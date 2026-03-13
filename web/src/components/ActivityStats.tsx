/**
 * Activity Stats Card Grid
 *
 * Renders 4 stat cards showing aggregated user reading activity.
 *
 * Responsibilities:
 * - Display total papers seen, read, saved, and reading time
 * - Format reading time from seconds into human-readable format (e.g. "2h 15m")
 */

import React from 'react';

// ============================================================================
// TYPES
// ============================================================================

interface ActivityStatsProps {
  /** Total number of papers expanded (previewed) */
  totalExpanded: number;
  /** Total number of papers read (scrolled past threshold) */
  totalRead: number;
  /** Total number of papers saved */
  totalSaved: number;
  /** Total active reading time across all reads, in seconds */
  totalReadingTimeSeconds: number;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Formats seconds into a human-readable duration string.
 * @param seconds - Total seconds to format
 * @returns Formatted string like "2h 15m", "45m", or "0m"
 */
function formatReadingTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

// ============================================================================
// COMPONENT
// ============================================================================

/**
 * Renders 4 stat cards in a responsive grid showing user activity totals.
 * @param props - Aggregated interaction stats
 * @returns Grid of stat cards
 */
export default function ActivityStats({
  totalExpanded,
  totalRead,
  totalSaved,
  totalReadingTimeSeconds,
}: ActivityStatsProps): React.JSX.Element {
  const cards = [
    { label: 'Papers seen', value: totalExpanded },
    { label: 'Papers read', value: totalRead },
    { label: 'Papers saved', value: totalSaved },
    { label: 'Reading time', value: formatReadingTime(totalReadingTimeSeconds) },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => (
        <div
          key={card.label}
          className="p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
        >
          <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">{card.value}</div>
          <div className="text-sm text-gray-600 dark:text-gray-400 mt-1">{card.label}</div>
        </div>
      ))}
    </div>
  );
}
