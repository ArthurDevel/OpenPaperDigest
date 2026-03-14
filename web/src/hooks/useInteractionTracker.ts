"use client";

/**
 * Interaction Tracker Hook
 *
 * Session-level tracker that collects user interaction events (expand, read, save, seen)
 * and flushes them to the backend API.
 *
 * Responsibilities:
 * - Buffer interaction events in memory
 * - Flush to POST /api/users/me/interactions every 15s or on page visibility change
 * - Use navigator.sendBeacon for reliable delivery on page unload
 * - Track which paper UUIDs the user has interacted with this session
 */

import { useRef, useEffect, useCallback } from 'react';
import type { InteractionEvent } from '../types/recommendation';
import { ensureAuthenticated } from '../lib/supabase/client';

// ============================================================================
// CONSTANTS
// ============================================================================

/** Interval in ms between automatic flushes */
const FLUSH_INTERVAL_MS = 15_000;
/** API endpoint for posting interaction events */
const INTERACTIONS_ENDPOINT = '/api/users/me/interactions';

// ============================================================================
// TYPES
// ============================================================================

export interface InteractionTrackerReturn {
  /** Track a paper expand event */
  trackExpand: (paperUuid: string) => void;
  /** Track a paper read event with reading ratio and active reading time */
  trackRead: (paperUuid: string, readingRatio: number, activeTimeSeconds: number) => void;
  /** Track a paper save event (only fires for non-anonymous users) */
  trackSave: (paperUuid: string) => void;
  /** Track a paper seen event (fired when a paper card scrolls into view) */
  trackSeen: (paperUuid: string) => void;
  /** Get all paper UUIDs interacted with this session */
  getSessionPaperUuids: () => string[];
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Sends buffered events to the backend via fetch.
 * @param events - Array of interaction events to send
 */
async function flushViaFetch(events: InteractionEvent[]): Promise<void> {
  await fetch(INTERACTIONS_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ events }),
  });
}

/**
 * Sends buffered events to the backend via sendBeacon (for page unload).
 * @param events - Array of interaction events to send
 */
function flushViaBeacon(events: InteractionEvent[]): void {
  const blob = new Blob(
    [JSON.stringify({ events })],
    { type: 'application/json' }
  );
  navigator.sendBeacon(INTERACTIONS_ENDPOINT, blob);
}

// ============================================================================
// MAIN EXPORT
// ============================================================================

/**
 * Session-level interaction tracker that buffers events and flushes to backend.
 * Ensures the user has an authenticated session (anonymous or permanent) before
 * flushing. Flushes every 15s, on visibility change, and on page unload.
 *
 * @returns Object with tracking functions and session paper UUID accessor
 */
export function useInteractionTracker(): InteractionTrackerReturn {
  const bufferRef = useRef<InteractionEvent[]>([]);
  const sessionPaperUuidsRef = useRef<Set<string>>(new Set());
  const flushingRef = useRef(false);

  // Flush buffered events to backend
  const flush = useCallback(async () => {
    if (bufferRef.current.length === 0 || flushingRef.current) return;

    const events = bufferRef.current.splice(0);
    flushingRef.current = true;

    try {
      await ensureAuthenticated();
      await flushViaFetch(events);
    } catch (error) {
      // Re-add events to buffer on failure so they can be retried
      bufferRef.current.unshift(...events);
      console.error('Failed to flush interactions:', error);
    } finally {
      flushingRef.current = false;
    }
  }, []);

  // Set up periodic flush, visibility change handler, and beforeunload
  useEffect(() => {
    // Ensure anonymous auth session exists on mount
    ensureAuthenticated().catch((error) => {
      console.error('Failed to establish anonymous session:', error);
    });

    const interval = setInterval(flush, FLUSH_INTERVAL_MS);

    const handleVisibilityChange = () => {
      if (document.hidden && bufferRef.current.length > 0) {
        flush();
      }
    };

    const handleBeforeUnload = () => {
      if (bufferRef.current.length > 0) {
        flushViaBeacon(bufferRef.current);
        bufferRef.current = [];
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('beforeunload', handleBeforeUnload);

      // Flush remaining events on unmount
      if (bufferRef.current.length > 0) {
        flushViaBeacon(bufferRef.current);
        bufferRef.current = [];
      }
    };
  }, [flush]);

  // ============================================================================
  // TRACKING METHODS
  // ============================================================================

  const trackExpand = useCallback((paperUuid: string) => {
    sessionPaperUuidsRef.current.add(paperUuid);
    bufferRef.current.push({
      paperUuid,
      interactionType: 'expanded',
    });
  }, []);

  const trackRead = useCallback((paperUuid: string, readingRatio: number, activeTimeSeconds: number) => {
    bufferRef.current.push({
      paperUuid,
      interactionType: 'read',
      metadata: { readingRatio, activeTimeSeconds },
    });
  }, []);

  const trackSave = useCallback((paperUuid: string) => {
    // trackSave only fires for permanent (non-anonymous) users.
    // The backend will validate the user type; we still send the event
    // and let the API route filter if needed.
    bufferRef.current.push({
      paperUuid,
      interactionType: 'saved',
    });
  }, []);

  /**
   * Track a paper seen (impression) event.
   * Deduplicates within the session: if the paper is already in
   * sessionPaperUuidsRef, the buffer push is skipped.
   * @param paperUuid - UUID of the paper that scrolled into view
   */
  const trackSeen = useCallback((paperUuid: string) => {
    // Skip if already tracked this session (handles remounts from scrolling)
    if (sessionPaperUuidsRef.current.has(paperUuid)) return;

    sessionPaperUuidsRef.current.add(paperUuid);
    bufferRef.current.push({
      paperUuid,
      interactionType: 'seen',
    });
  }, []);

  const getSessionPaperUuids = useCallback((): string[] => {
    return Array.from(sessionPaperUuidsRef.current);
  }, []);

  return { trackExpand, trackRead, trackSave, trackSeen, getSessionPaperUuids };
}
