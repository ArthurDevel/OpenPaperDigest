"use client";

/**
 * Reading Tracker Hook
 *
 * Measures active reading time for an expanded paper summary using
 * IntersectionObserver + activity heartbeat.
 *
 * Responsibilities:
 * - Track whether the summary div is visible in the viewport
 * - Detect user activity (scroll, mouse, touch) within the summary div
 * - Accumulate active reading time and compute a reading ratio
 * - Fire a callback with reading time when the paper collapses/unmounts
 */

import { useRef, useCallback } from 'react';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Activity timeout -- user is "inactive" if no event for this many ms */
const ACTIVITY_TIMEOUT_MS = 15_000;
/** Throttle interval for activity event listeners */
const ACTIVITY_THROTTLE_MS = 300;
/** Heartbeat interval in ms for accumulating active time */
const HEARTBEAT_MS = 1000;

// ============================================================================
// TYPES
// ============================================================================

export interface ReadingTrackerResult {
  /** Callback ref to attach to the expanded summary content div */
  ref: (node: HTMLDivElement | null) => void;
  /** Whether the user is currently actively reading */
  isActivelyReading: boolean;
}

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Tracks active reading time for an expanded paper summary.
 * Uses a callback ref to start/stop tracking when the element mounts/unmounts.
 * Sets up IntersectionObserver for visibility and activity listeners
 * (scroll, mousemove, touchstart) scoped to the summary div.
 * Fires onReadComplete when the element unmounts (paper collapses) if any
 * active reading time was accumulated.
 *
 * @param paperUuid - UUID of the paper being read
 * @param wordCount - Number of words in the summary
 * @param onReadComplete - Callback fired with (paperUuid, wordCount, activeTimeSeconds) on unmount
 * @returns Object with callback ref to attach to the summary div and active reading state
 */
export function useReadingTracker(
  paperUuid: string,
  wordCount: number,
  onReadComplete: (paperUuid: string, wordCount: number, activeTimeSeconds: number) => void
): ReadingTrackerResult {
  const isActivelyReadingRef = useRef(false);
  const cleanupRef = useRef<(() => void) | null>(null);

  // Callback ref: sets up tracking when element mounts, tears down on unmount
  const ref = useCallback((node: HTMLDivElement | null) => {
    // Tear down previous tracking if any
    if (cleanupRef.current) {
      cleanupRef.current();
      cleanupRef.current = null;
    }

    if (!node) return;

    // -- Tracking state for this element lifecycle --
    let isInViewport = false;
    let lastActivity = Date.now();
    let activeTimeMs = 0;
    let lastTick = Date.now();
    let lastThrottled = 0;

    // -- Activity tracking (throttled) --
    const handleActivity = () => {
      const now = Date.now();
      if (now - lastThrottled < ACTIVITY_THROTTLE_MS) return;
      lastThrottled = now;
      lastActivity = now;
    };

    node.addEventListener('scroll', handleActivity, { passive: true });
    node.addEventListener('mousemove', handleActivity, { passive: true });
    node.addEventListener('touchstart', handleActivity, { passive: true });

    // -- IntersectionObserver --
    const observer = new IntersectionObserver(
      ([entry]) => {
        isInViewport = entry.isIntersecting;
        if (entry.isIntersecting) {
          lastActivity = Date.now();
          lastTick = Date.now();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(node);

    // -- Heartbeat interval to accumulate active time --
    const interval = setInterval(() => {
      const now = Date.now();
      const isActive = isInViewport && (now - lastActivity < ACTIVITY_TIMEOUT_MS);

      isActivelyReadingRef.current = isActive;

      if (isActive && lastTick > 0) {
        activeTimeMs += now - lastTick;
      }
      lastTick = now;
    }, HEARTBEAT_MS);

    // -- Cleanup function: called when element unmounts or ref changes --
    cleanupRef.current = () => {
      // Accumulate any final active time
      const now = Date.now();
      const isActive = isInViewport && (now - lastActivity < ACTIVITY_TIMEOUT_MS);
      if (isActive && lastTick > 0) {
        activeTimeMs += now - lastTick;
      }

      // Fire callback if any reading time was accumulated
      if (activeTimeMs > 0) {
        onReadComplete(paperUuid, wordCount, Math.round(activeTimeMs / 1000));
      }

      clearInterval(interval);
      observer.disconnect();
      node.removeEventListener('scroll', handleActivity);
      node.removeEventListener('mousemove', handleActivity);
      node.removeEventListener('touchstart', handleActivity);
      isActivelyReadingRef.current = false;
    };
  }, [paperUuid, wordCount, onReadComplete]);

  return {
    ref,
    isActivelyReading: isActivelyReadingRef.current,
  };
}
