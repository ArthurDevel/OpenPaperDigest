import { useRef, useEffect, useCallback } from 'react';

declare global {
  interface Window {
    umami?: {
      track: (event: string, data?: Record<string, any>) => void;
    };
  }
}

/**
 * Custom hook to track when a paper is visible in the viewport.
 * Fires a 'paper-seen' event to Umami analytics.
 * @param paperUuid - The UUID of the paper to track.
 * @param enabled - Whether the hook is active.
 * @returns A ref to attach to the element to be observed.
 */
export const usePaperImpression = (paperUuid: string, enabled: boolean) => {
  const ref = useRef<HTMLDivElement>(null);
  const hasBeenSeen = useRef(false);

  const trackImpression = useCallback(() => {
    if (window.umami) {
      window.umami.track('paper-seen', { paper_uuid: paperUuid });
    }
  }, [paperUuid]);

  useEffect(() => {
    if (!enabled || !ref.current || hasBeenSeen.current) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          if (!hasBeenSeen.current) {
            hasBeenSeen.current = true;
            trackImpression();
          }
          // Disconnect the observer once the element has been seen
          observer.disconnect();
        }
      },
      {
        threshold: 0.1, // Fire when 10% of the element is visible
      }
    );

    observer.observe(ref.current);

    return () => {
      observer.disconnect();
    };
  }, [enabled, trackImpression]);

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
