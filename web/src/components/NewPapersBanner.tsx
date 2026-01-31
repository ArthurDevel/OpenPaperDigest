'use client';

import { useEffect, useState } from 'react';
import { X, Bell } from 'lucide-react';
import { countPapersSince, listMinimalPapersPaginated } from '../services/api';
import { getLastVisitTimestamp, setLastVisitTimestamp } from '../utils/lastVisitStorage';

// DAG runs at 2:00 AM UTC and 2:00 PM UTC
const UTC_BATCH_HOURS = [2, 14];

/**
 * Calculates the next scheduled batch time.
 * DAG runs at 2:00 AM UTC and 2:00 PM UTC daily.
 * @returns Date object representing the next batch time, or null if calculation fails
 */
const getNextBatchTime = (): Date | null => {
  try {
    const now = new Date();
    
    // Create Date objects for today's batch times in UTC
    const batchTimes: Date[] = [];
    for (const utcHour of UTC_BATCH_HOURS) {
      const batchTime = new Date(Date.UTC(
        now.getUTCFullYear(),
        now.getUTCMonth(),
        now.getUTCDate(),
        utcHour,
        0,
        0
      ));
      batchTimes.push(batchTime);
    }
    
    // Sort by time to ensure correct order
    batchTimes.sort((a, b) => a.getTime() - b.getTime());
    
    // Find next occurrence today
    for (const batchTime of batchTimes) {
      if (batchTime > now) {
        return batchTime;
      }
    }
    
    // If both times have passed today, next batch is tomorrow's first batch (2 AM UTC)
    const tomorrowUtc2am = new Date(Date.UTC(
      now.getUTCFullYear(),
      now.getUTCMonth(),
      now.getUTCDate() + 1,
      2,
      0,
      0
    ));
    
    return tomorrowUtc2am;
  } catch (error) {
    console.error('Failed to calculate next batch time:', error);
    return null;
  }
};

/**
 * Formats time remaining as "HHhMM"
 * @param milliseconds - Time remaining in milliseconds
 * @returns Formatted string like "03h24" or "12h05"
 */
const formatTimeRemaining = (milliseconds: number): string => {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  
  return `${hours.toString().padStart(2, '0')}h${minutes.toString().padStart(2, '0')}`;
};

/**
 * Banner component that shows how many papers have been added since last visit.
 * If no new papers, shows total papers indexed with countdown.
 * Can be manually dismissed.
 * Also displays countdown to next scheduled batch.
 */
export default function NewPapersBanner() {
  const [newCount, setNewCount] = useState<number | null>(null);
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const [isVisible, setIsVisible] = useState<boolean>(false);
  const [isDismissed, setIsDismissed] = useState<boolean>(false);
  const [timeRemaining, setTimeRemaining] = useState<string | null>(null);

  useEffect(() => {
    const checkNewPapers = async (): Promise<void> => {
      const lastVisit = getLastVisitTimestamp();
      
      // If no localStorage, set it immediately
      if (!lastVisit) {
        setLastVisitTimestamp();
      }

      try {
        // Fetch total count of papers
        const totalResult = await listMinimalPapersPaginated(1, 1);
        setTotalCount(totalResult.total);

        // Check for new papers since last visit
        if (lastVisit) {
          const result = await countPapersSince(lastVisit);
          const count = result.count;
          setNewCount(count);
          
          if (count > 0) {
            setIsVisible(true);
          } else {
            // No new papers, but show banner with total count
            setIsVisible(true);
            setLastVisitTimestamp();
          }
        } else {
          // No last visit timestamp, show banner with total count
          setIsVisible(true);
        }
      } catch (error) {
        // Fail silently - don't show banner on error
        console.error('Failed to check papers:', error);
      }
    };

    checkNewPapers();
  }, []);

  // Update localStorage after 5 seconds when banner is visible with new papers
  useEffect(() => {
    if (!isVisible || isDismissed) {
      return;
    }

    const hasNewPapers = newCount !== null && newCount > 0;
    
    if (hasNewPapers) {
      const timer = setTimeout(() => {
        setLastVisitTimestamp();
      }, 5000);

      return () => {
        clearTimeout(timer);
      };
    }
  }, [isVisible, isDismissed, newCount]);

  // Countdown timer for next batch
  useEffect(() => {
    const updateCountdown = (): void => {
      const nextBatchTime = getNextBatchTime();
      if (!nextBatchTime) {
        setTimeRemaining(null);
        return;
      }

      const now = new Date();
      const remaining = nextBatchTime.getTime() - now.getTime();
      
      if (remaining > 0) {
        setTimeRemaining(formatTimeRemaining(remaining));
      } else {
        // If time has passed, recalculate (shouldn't happen often, but handles edge cases)
        setTimeRemaining(null);
      }
    };

    // Update immediately
    updateCountdown();

    // Update every second
    const interval = setInterval(updateCountdown, 1000);

    return () => {
      clearInterval(interval);
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

  if (!isVisible || isDismissed || totalCount === null) {
    return null;
  }

  const hasNewPapers = newCount !== null && newCount > 0;

  return (
    <div className="mb-6 w-full bg-blue-50 dark:bg-slate-800 border border-blue-100 dark:border-blue-800 rounded-lg p-4 flex items-start gap-3 shadow-sm transition-all">
      <div className="flex-shrink-0 text-blue-600 dark:text-blue-400 mt-0.5">
        <Bell size={20} />
      </div>
      <div className="flex-1 pt-0.5">
        {hasNewPapers ? (
          <>
            <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
              New Papers Available
            </p>
            <p className="text-sm text-blue-600 dark:text-blue-300 mt-0.5">
              {newCount === 1 ? (
                <span>1 new paper has been added since your last visit.</span>
              ) : (
                <span>{newCount} new papers have been added since your last visit.</span>
              )}
            </p>
            {timeRemaining && (
              <p className="text-sm text-blue-600 dark:text-blue-300 mt-1">
                Next batch scheduled in{' '}
                <span
                  className="font-mono font-bold inline-block"
                  style={{
                    textShadow: '0 1px 2px rgba(0, 0, 0, 0.1), 0 0 1px rgba(255, 255, 255, 0.3)',
                    animation: 'subtle-pulse 2s ease-in-out infinite',
                  }}
                >
                  {timeRemaining}
                </span>
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm font-medium text-blue-800 dark:text-blue-200">
              Adding new papers twice a day!
            </p>
            {timeRemaining && (
              <p className="text-sm text-blue-600 dark:text-blue-300 mt-1">
                Next batch of new papers scheduled in{' '}
                <span
                  className="font-mono font-bold inline-block"
                  style={{
                    textShadow: '0 1px 2px rgba(0, 0, 0, 0.1), 0 0 1px rgba(255, 255, 255, 0.3)',
                    animation: 'subtle-pulse 2s ease-in-out infinite',
                  }}
                >
                  {timeRemaining}
                </span>
              </p>
            )}
          </>
        )}
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
