'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { countPapersSince } from '../services/api';
import { getLastVisitTimestamp, setLastVisitTimestamp } from '../utils/lastVisitStorage';

/**
 * Banner component that shows how many papers have been added since last visit.
 * Auto-dismisses after 10 seconds and can be manually dismissed.
 * Only shows if there are new papers and localStorage exists.
 */
export default function NewPapersBanner() {
  const [count, setCount] = useState<number | null>(null);
  const [isVisible, setIsVisible] = useState<boolean>(false);
  const [isDismissed, setIsDismissed] = useState<boolean>(false);

  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;

    const checkNewPapers = async (): Promise<void> => {
      const lastVisit = getLastVisitTimestamp();
      
      // If no localStorage, set it immediately and don't show banner
      if (!lastVisit) {
        setLastVisitTimestamp();
        return;
      }

      try {
        const result = await countPapersSince(lastVisit);
        const newCount = result.count;
        
        if (newCount > 0) {
          setCount(newCount);
          setIsVisible(true);
          
          // Auto-dismiss after 10 seconds
          timer = setTimeout(() => {
            setIsDismissed(true);
            setIsVisible(false);
            setLastVisitTimestamp();
          }, 10000);
        } else {
          // No new papers, update timestamp immediately
          setLastVisitTimestamp();
        }
      } catch (error) {
        // Fail silently - don't show banner on error
        console.error('Failed to check new papers:', error);
      }
    };

    checkNewPapers();

    return () => {
      if (timer !== null) {
        clearTimeout(timer);
      }
    };
  }, []);

  /**
   * Handles banner dismissal and updates localStorage
   */
  const handleDismiss = (): void => {
    setIsDismissed(true);
    setIsVisible(false);
    setLastVisitTimestamp();
  };

  if (!isVisible || isDismissed || count === null || count === 0) {
    return null;
  }

  return (
    <div className="w-full bg-indigo-600 dark:bg-indigo-700 text-white px-4 sm:px-6 lg:px-10 py-3 flex items-center justify-between">
      <div className="flex-1 text-sm">
        {count === 1 ? (
          <span>1 new paper added since you last opened from this device</span>
        ) : (
          <span>{count} new papers added since you last opened from this device</span>
        )}
      </div>
      <button
        onClick={handleDismiss}
        className="ml-4 flex-shrink-0 inline-flex items-center justify-center p-1 rounded-md hover:bg-indigo-700 dark:hover:bg-indigo-600 transition-colors"
        aria-label="Dismiss banner"
      >
        <X size={18} />
      </button>
    </div>
  );
}

