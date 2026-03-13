'use client';

/**
 * User Activity Page
 *
 * Displays aggregated reading activity stats and a chronological reading history.
 *
 * Responsibilities:
 * - Fetch interaction stats from the API
 * - Render ActivityStats card grid and ReadingHistory table
 * - Handle loading, error, and empty states
 */

import React, { useEffect, useState } from 'react';
import { useSession } from '@/services/auth';
import { Loader } from 'lucide-react';
import type { InteractionStats } from '@/types/recommendation';
import ActivityStats from '@/components/ActivityStats';
import ReadingHistory from '@/components/ReadingHistory';

// ============================================================================
// COMPONENT
// ============================================================================

/**
 * Fetches user interaction stats and renders activity overview.
 * @returns Activity page with stat cards and reading history table
 */
export default function UserActivityPage(): React.JSX.Element {
  const { user } = useSession();
  const [stats, setStats] = useState<InteractionStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  // Fetch interaction stats
  useEffect(() => {
    const run = async () => {
      if (!user?.id) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const res = await fetch('/api/users/me/interactions/stats');
        if (!res.ok) {
          throw new Error('Failed to load activity stats');
        }
        const data: InteractionStats = await res.json();
        setStats(data);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load activity stats';
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [user?.id]);

  if (!user?.id) {
    return (
      <div className="p-6 h-full flex flex-col min-h-0">
        <h1 className="text-xl font-semibold mb-2">My activity</h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">Please sign in to view your activity.</p>
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col min-h-0">
      <h1 className="text-xl font-semibold">My activity</h1>
      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 mb-4">Your reading activity and stats.</p>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
            <Loader className="animate-spin w-4 h-4 mr-2" /> Loading...
          </div>
        ) : stats ? (
          <div className="h-full overflow-auto space-y-6">
            <ActivityStats
              totalExpanded={stats.totalExpanded}
              totalRead={stats.totalRead}
              totalSaved={stats.totalSaved}
              totalReadingTimeSeconds={stats.totalReadingTimeSeconds}
            />
            <div>
              <h2 className="text-lg font-semibold mb-3">Reading history</h2>
              <ReadingHistory items={stats.readingHistory} />
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-600 dark:text-gray-300">No activity yet.</p>
        )}
      </div>
    </div>
  );
}
