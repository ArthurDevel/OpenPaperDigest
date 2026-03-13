"use client";

/**
 * Users Overview Page (Admin)
 *
 * Displays summary stats and a table of all registered users.
 * - Total user count and new users in the last 7 / 30 days
 * - Sortable table with email, signup date, saved papers count, requests count
 */

import { useEffect, useState } from 'react';
import { listUsers, type AdminUserItem } from '../../../services/api';
import Link from 'next/link';

// ============================================================================
// CONSTANTS
// ============================================================================

const DAYS_7 = 7 * 24 * 60 * 60 * 1000;
const DAYS_30 = 30 * 24 * 60 * 60 * 1000;

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * Summary stat card displayed at the top of the page.
 */
function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm px-6 py-4">
      <div className="text-sm text-gray-500 dark:text-gray-400">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}

// ============================================================================
// MAIN PAGE
// ============================================================================

export default function UsersPage() {
  const [users, setUsers] = useState<AdminUserItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await listUsers();
        setUsers(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  // ============================================================================
  // HELPER FUNCTIONS
  // ============================================================================

  const now = Date.now();
  const totalUsers = users.length;
  const newLast7Days = users.filter(
    (u) => now - new Date(u.createdAt).getTime() < DAYS_7
  ).length;
  const newLast30Days = users.filter(
    (u) => now - new Date(u.createdAt).getTime() < DAYS_30
  ).length;

  /**
   * Format an ISO date string for display.
   * @param dateStr - ISO date string
   * @returns Formatted date string
   */
  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="px-6 py-6 text-gray-900 dark:text-gray-100">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Users</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            All registered users and their activity
          </p>
        </div>
        <Link
          href="/management"
          className="px-4 py-2 rounded-md bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
        >
          Back to Management
        </Link>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center h-96">
          <div>Loading...</div>
        </div>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-1 sm:grid-cols-3 gap-4">
            <StatCard label="Total Users" value={totalUsers} />
            <StatCard label="New (last 7 days)" value={newLast7Days} />
            <StatCard label="New (last 30 days)" value={newLast30Days} />
          </div>

          <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm">
            <div className="px-6 py-3 text-sm font-semibold border-b border-gray-200 dark:border-gray-700">
              All Users ({totalUsers})
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Email</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Signed Up</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Saved Papers</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Requests</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{user.email}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{formatDate(user.createdAt)}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{user.savedPapersCount}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{user.requestsCount}</td>
                    </tr>
                  ))}
                  {users.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                        No users found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
