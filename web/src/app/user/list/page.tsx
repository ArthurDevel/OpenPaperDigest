'use client';

import React, { useEffect, useState } from 'react';
import { useSession } from '@/services/auth';
import { getMyUserList, type UserListItem, removePaperFromUserList } from '@/services/users';
import { Loader } from 'lucide-react';

/**
 * User's paper list page showing saved papers.
 * @returns Page component displaying user's saved papers in a table
 */
export default function UserListPage() {
  const { user } = useSession();
  const [items, setItems] = useState<UserListItem[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [removing, setRemoving] = useState<string | null>(null);

  // Fetch user's paper list
  useEffect(() => {
    const run = async () => {
      if (!user?.id) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const list = await getMyUserList();
        setItems(list);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load your list';
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [user?.id]);

  /**
   * Handles removing a paper from the list
   * @param paperUuid - UUID of the paper to remove
   */
  const handleRemove = async (paperUuid: string): Promise<void> => {
    if (!user?.id) return;
    try {
      setRemoving(paperUuid);
      await removePaperFromUserList(paperUuid);
      setItems((prev) => (prev || []).filter((it) => it.paperUuid !== paperUuid));
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to remove';
      alert(message);
    } finally {
      setRemoving(null);
    }
  };

  if (!user?.id) {
    return (
      <div className="p-6 h-full flex flex-col min-h-0">
        <h1 className="text-xl font-semibold mb-2">My list</h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">Please sign in to view your saved papers.</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">If you save papers, they will appear here.</p>
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col min-h-0">
      <h1 className="text-xl font-semibold">My list</h1>
      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 mb-4">If you save papers, they will appear here.</p>
      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300 text-sm">{error}</div>
      )}
      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
            <Loader className="animate-spin w-4 h-4 mr-2" /> Loading...
          </div>
        ) : (
          <div className="h-full overflow-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left border-b border-gray-200 dark:border-gray-700">
                  <th className="p-2 w-24">Image</th>
                  <th className="p-2">Title & Authors</th>
                  <th className="p-2 w-40">Date added</th>
                  <th className="p-2 w-40">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(items || []).map((it) => {
                  const href = `/paper/${encodeURIComponent(it.slug || it.paperUuid)}`;
                  const added = it.createdAt ? new Date(it.createdAt) : null;
                  const addedStr = added ? added.toLocaleDateString() + ' ' + added.toLocaleTimeString() : '-';
                  return (
                    <tr key={it.paperUuid} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="p-2 align-top">
                        {it.thumbnailDataUrl ? (
                          <a href={href}>
                            <img src={it.thumbnailDataUrl} alt="" className="w-20 h-14 object-cover rounded" />
                          </a>
                        ) : (
                          <div className="w-20 h-14 bg-gray-200 dark:bg-gray-700 rounded" />
                        )}
                      </td>
                      <td className="p-2 align-top">
                        <a href={href} className="font-medium hover:underline">{it.title || it.paperUuid}</a>
                        {it.authors && (
                          <div className="text-xs text-gray-600 dark:text-gray-400 truncate">{it.authors}</div>
                        )}
                      </td>
                      <td className="p-2 align-top whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">{addedStr}</td>
                      <td className="p-2 align-top">
                        <div className="flex gap-2">
                          <a href={href} className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600">View</a>
                          <button
                            onClick={() => handleRemove(it.paperUuid)}
                            disabled={removing === it.paperUuid}
                            className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
                          >
                            {removing === it.paperUuid ? 'Removing...' : 'Remove'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {items && items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="p-4 text-sm text-gray-600 dark:text-gray-300">Your list is empty.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
