/**
 * Reading History Table
 *
 * Renders a table of recently opened papers with reading time details.
 *
 * Responsibilities:
 * - Display paper title (linked to paper page when slug is available)
 * - Show total reading time and last-opened date
 * - Show paper thumbnail when available
 */

import React from 'react';
import type { ReadingHistoryItem } from '@/types/recommendation';

// ============================================================================
// TYPES
// ============================================================================

interface ReadingHistoryProps {
  /** List of reading history entries to display */
  items: ReadingHistoryItem[];
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Formats seconds into a short duration string.
 * @param seconds - Duration in seconds
 * @returns Formatted string like "5m 30s", "12s", or "-" for 0
 */
function formatDuration(seconds: number): string {
  if (seconds === 0) return '-';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) {
    return `${mins}m ${secs}s`;
  }
  return `${secs}s`;
}

/**
 * Formats an ISO date string into a readable date/time.
 * @param isoString - ISO 8601 timestamp
 * @returns Formatted date string
 */
function formatDate(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// ============================================================================
// COMPONENT
// ============================================================================

/**
 * Renders a table of opened papers with title, reading time, and last-opened date.
 * @param props - Reading history items
 * @returns Table of reading history entries
 */
export default function ReadingHistory({ items }: ReadingHistoryProps): React.JSX.Element {
  if (items.length === 0) {
    return <p className="text-sm text-gray-600 dark:text-gray-300">No reading history yet.</p>;
  }

  return (
    <div className="overflow-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="text-left border-b border-gray-200 dark:border-gray-700">
            <th className="p-2 w-24">Image</th>
            <th className="p-2">Title</th>
            <th className="p-2 w-28">Reading time</th>
            <th className="p-2 w-40">Last opened</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const href = item.slug
              ? `/paper/${encodeURIComponent(item.slug)}`
              : `/paper/${encodeURIComponent(item.paperUuid)}`;

            return (
              <tr key={item.paperUuid} className="border-b border-gray-100 dark:border-gray-800">
                <td className="p-2 align-top">
                  {item.thumbnailUrl ? (
                    <a href={href}>
                      <img src={item.thumbnailUrl} alt="" className="w-20 h-14 object-cover rounded" />
                    </a>
                  ) : (
                    <div className="w-20 h-14 bg-gray-200 dark:bg-gray-700 rounded" />
                  )}
                </td>
                <td className="p-2 align-top">
                  <a href={href} className="font-medium hover:underline">
                    {item.title || item.paperUuid}
                  </a>
                  {item.authors && (
                    <div className="text-xs text-gray-600 dark:text-gray-400 truncate">{item.authors}</div>
                  )}
                </td>
                <td className="p-2 align-top whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                  {formatDuration(item.activeTimeSeconds)}
                </td>
                <td className="p-2 align-top whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                  {formatDate(item.lastOpenedAt)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
