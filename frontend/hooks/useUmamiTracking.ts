import { useRef, useEffect, useCallback } from 'react';

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: Record<string, any>) => void;
    };
  }
}

/**
 * Custom hook to track when a paper is visible in the viewport and for how long.
 * - Fires a 'paper-seen' event to Umami analytics once per paper.
 * - Fires a 'paper-in-view-duration' event with the duration in milliseconds
 *   each time the paper leaves the viewport or the tab is hidden.
 * @param paperUuid - The UUID of the paper to track.
 * @param enabled - Whether the hook is active.
 * @returns A ref to attach to the element to be observed.
 */
export const usePaperImpression = (paperUuid: string, enabled: boolean) => {
  const ref = useRef<HTMLDivElement>(null);
  const hasBeenSeen = useRef(false);
  const startTime = useRef<number | null>(null);
  const isIntersecting = useRef(false);

  const trackDuration = useCallback(() => {
    if (startTime.current && window.umami) {
      const duration = Date.now() - startTime.current;
      // Only send event if duration is meaningful (e.g., > 100ms)
      if (duration > 100) {
        window.umami.track('paper-in-view-duration', { paper_uuid: paperUuid, duration_ms: duration });
      }
      startTime.current = null; // Reset timer
    }
  }, [paperUuid]);

  const trackImpression = useCallback(() => {
    if (window.umami) {
      window.umami.track('paper-seen', { paper_uuid: paperUuid });
    }
  }, [paperUuid]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        // User switched away, track duration if the element was visible
        if (isIntersecting.current) {
          trackDuration();
        }
      } else {
        // User came back, restart timer if the element is still visible
        if (isIntersecting.current) {
          startTime.current = Date.now();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [trackDuration]);

  useEffect(() => {
    if (!enabled || !ref.current) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        isIntersecting.current = entry.isIntersecting;

        if (entry.isIntersecting) {
          // Element is in view
          if (!hasBeenSeen.current) {
            hasBeenSeen.current = true;
            trackImpression();
          }
          // Start the timer
          startTime.current = Date.now();
        } else {
          // Element is out of view, track duration
          trackDuration();
        }
      },
      {
        threshold: 0.1,
      }
    );

    const currentElement = ref.current;
    observer.observe(currentElement);

    return () => {
      trackDuration(); // Track any final duration when the component unmounts
      observer.unobserve(currentElement);
    };
  }, [enabled, trackImpression, trackDuration]);

  return ref;
};

/**
 * Tracks a 'paper-opened' event with Umami.
 * @param paperUuid - The UUID of the paper that was opened.
 */
export const trackPaperOpened = (paperUuid: string) => {
  if (window.umami) {
    window.umami.track('paper-opened', { paper_uuid: paperUuid });
  }
};
