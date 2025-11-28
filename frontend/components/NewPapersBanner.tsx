'use client';

import { useEffect, useState } from 'react';
import { X, Bell } from 'lucide-react';
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
    <div className="mb-6 w-full bg-blue-50 dark:bg-slate-800 border border-blue-100 dark:border-blue-800 rounded-lg p-4 flex items-start gap-3 shadow-sm transition-all">
      <div className="flex-shrink-0 text-blue-600 dark:text-blue-400 mt-0.5">
        <Bell size={20} />
      </div>
      <div className="flex-1 pt-0.5">
        <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
          New Papers Available
        </p>
        <p className="text-sm text-blue-600 dark:text-blue-300 mt-0.5">
          {count === 1 ? (
            <span>1 new paper has been added since your last visit.</span>
          ) : (
            <span>{count} new papers have been added since your last visit.</span>
          )}
        </p>
      </div>
      <button
        onClick={handleDismiss}
        className="flex-shrink-0 -mr-1 -mt-1 p-1.5 rounded-md text-blue-500 hover:bg-blue-100 dark:text-blue-400 dark:hover:bg-slate-700 transition-colors"
        aria-label="Dismiss banner"
      >
        <X size={16} />
      </button>
    </div>
  );
}
