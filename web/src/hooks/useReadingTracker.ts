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
 * - Fire a callback when the paper collapses/unmounts if readingRatio > 0.4
 */

import { useRef, useEffect, useCallback } from 'react';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Words per minute reading speed assumption */
const READING_SPEED_WPM = 200;
/** Minimum reading ratio to trigger the onReadComplete callback */
const MIN_READING_RATIO = 0.4;
/** Activity timeout -- user is "inactive" if no event for this many ms */
const ACTIVITY_TIMEOUT_MS = 15_000;
/** Throttle interval for activity event listeners */
const ACTIVITY_THROTTLE_MS = 300;

// ============================================================================
// TYPES
// ============================================================================

export interface ReadingTrackerResult {
  /** Ref to attach to the expanded summary content div */
  ref: React.RefObject<HTMLDivElement | null>;
  /** Whether the user is currently actively reading */
  isActivelyReading: boolean;
}

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Tracks active reading time for an expanded paper summary.
 * Uses IntersectionObserver to detect visibility and activity listeners
 * (scroll, mousemove, touchstart) scoped to the summary div.
 * Fires onReadComplete when the paper collapses or unmounts if the user
 * read for at least 40% of the expected reading time.
 *
 * @param paperUuid - UUID of the paper being read
 * @param wordCount - Number of words in the summary
 * @param onReadComplete - Callback fired with (paperUuid, readingRatio) when reading ends
 * @returns Object with ref to attach to the summary div and active reading state
 */
export function useReadingTracker(
  paperUuid: string,
  wordCount: number,
  onReadComplete: (paperUuid: string, readingRatio: number) => void
): ReadingTrackerResult {
  const ref = useRef<HTMLDivElement | null>(null);
  const isActivelyReadingRef = useRef(false);
  const isInViewportRef = useRef(false);
  const lastActivityRef = useRef<number>(0);
  const activeTimeRef = useRef<number>(0);
  const lastTickRef = useRef<number>(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasFiredRef = useRef(false);

  // Expected reading time in ms
  const expectedReadingTimeMs = (wordCount / READING_SPEED_WPM) * 60 * 1000;

  // Fire the callback if enough reading happened
  const fireIfQualified = useCallback(() => {
    if (hasFiredRef.current || expectedReadingTimeMs <= 0) return;

    const ratio = activeTimeRef.current / expectedReadingTimeMs;
    if (ratio > MIN_READING_RATIO) {
      hasFiredRef.current = true;
      onReadComplete(paperUuid, ratio);
    }
  }, [paperUuid, expectedReadingTimeMs, onReadComplete]);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    // -- Activity tracking (throttled) --
    let lastThrottled = 0;
    const handleActivity = () => {
      const now = Date.now();
      if (now - lastThrottled < ACTIVITY_THROTTLE_MS) return;
      lastThrottled = now;
      lastActivityRef.current = now;
    };

    element.addEventListener('scroll', handleActivity, { passive: true });
    element.addEventListener('mousemove', handleActivity, { passive: true });
    element.addEventListener('touchstart', handleActivity, { passive: true });

    // -- IntersectionObserver --
    const observer = new IntersectionObserver(
      ([entry]) => {
        isInViewportRef.current = entry.isIntersecting;
        if (entry.isIntersecting) {
          // Start tracking -- mark activity so the first tick counts
          lastActivityRef.current = Date.now();
          lastTickRef.current = Date.now();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(element);

    // -- Heartbeat interval to accumulate active time --
    intervalRef.current = setInterval(() => {
      const now = Date.now();
      const isActive = isInViewportRef.current
        && (now - lastActivityRef.current < ACTIVITY_TIMEOUT_MS);

      isActivelyReadingRef.current = isActive;

      if (isActive && lastTickRef.current > 0) {
        activeTimeRef.current += now - lastTickRef.current;
      }
      lastTickRef.current = now;
    }, 1000);

    // -- Cleanup --
    return () => {
      // Accumulate any final active time
      const now = Date.now();
      const isActive = isInViewportRef.current
        && (now - lastActivityRef.current < ACTIVITY_TIMEOUT_MS);
      if (isActive && lastTickRef.current > 0) {
        activeTimeRef.current += now - lastTickRef.current;
      }

      fireIfQualified();

      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
      observer.disconnect();

      element.removeEventListener('scroll', handleActivity);
      element.removeEventListener('mousemove', handleActivity);
      element.removeEventListener('touchstart', handleActivity);
    };
  }, [fireIfQualified]);

  return {
    ref,
    isActivelyReading: isActivelyReadingRef.current,
  };
}
