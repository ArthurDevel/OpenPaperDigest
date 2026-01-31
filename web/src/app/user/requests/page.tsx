'use client';

import React, { useEffect, useState } from 'react';
import { useSession } from '@/services/auth';
import { listMyRequests, type UserRequestItem, removeUserRequest } from '@/services/requests';
import { Loader } from 'lucide-react';

/**
 * User's paper requests page showing requested papers.
 * @returns Page component displaying user's paper processing requests
 */
export default function UserRequestsPage() {
  const { user } = useSession();
  const [items, setItems] = useState<UserRequestItem[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [removing, setRemoving] = useState<string | null>(null);

  // Fetch user's paper requests
  useEffect(() => {
    const run = async () => {
      if (!user?.id) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const list = await listMyRequests();
        setItems(list);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load your requests';
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [user?.id]);

  /**
   * Handles removing a paper request
   * @param arxivId - arXiv ID of the paper to remove
   */
  const handleRemove = async (arxivId: string): Promise<void> => {
    if (!user?.id) return;
    try {
      setRemoving(arxivId);
      await removeUserRequest(arxivId);
      setItems((prev) => (prev || []).filter((it) => it.arxivId !== arxivId));
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to remove request';
      alert(message);
    } finally {
      setRemoving(null);
    }
  };

  if (!user?.id) {
    return (
      <div className="p-6 h-full flex flex-col min-h-0">
        <h1 className="text-xl font-semibold mb-2">My requests</h1>
        <p className="text-sm text-gray-600 dark:text-gray-300">Please sign in to view your requested papers.</p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">When you request papers, they will appear here.</p>
      </div>
    );
  }

  return (
    <div className="p-6 h-full flex flex-col min-h-0">
      <h1 className="text-xl font-semibold">My requests</h1>
      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 mb-4">When you request papers, they will appear here.</p>
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
                  <th className="p-2">arXiv ID</th>
                  <th className="p-2">Title & Authors</th>
                  <th className="p-2 w-40">Date requested</th>
                  <th className="p-2 w-40">Actions</th>
                </tr>
              </thead>
              <tbody>
                {(items || []).map((it) => {
                  const added = it.createdAt ? new Date(it.createdAt) : null;
                  const addedStr = added ? added.toLocaleDateString() + ' ' + added.toLocaleTimeString() : '-';
                  const absHref = `https://arxiv.org/abs/${encodeURIComponent(it.arxivId)}`;
                  return (
                    <tr key={it.arxivId} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="p-2 align-top">
                        <a href={absHref} target="_blank" rel="noopener noreferrer" className="font-medium hover:underline">
                          {it.arxivId}
                        </a>
                      </td>
                      <td className="p-2 align-top">
                        {it.title ? (
                          <div className="font-medium flex items-center gap-2">
                            <span>{it.title}</span>
                            {it.isProcessed && it.processedSlug ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">Processed</span>
                            ) : null}
                          </div>
                        ) : (
                          <div className="text-gray-500 dark:text-gray-400 italic">No title</div>
                        )}
                        {it.authors && (
                          <div className="text-xs text-gray-600 dark:text-gray-400 truncate">{it.authors}</div>
                        )}
                      </td>
                      <td className="p-2 align-top whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">{addedStr}</td>
                      <td className="p-2 align-top">
                        <div className="flex gap-2">
                          {it.isProcessed && it.processedSlug ? (
                            <a
                              href={`/paper/${encodeURIComponent(it.processedSlug)}`}
                              className="text-xs px-2 py-1 rounded border bg-green-600 text-white hover:bg-green-700 dark:border-green-700"
                            >
                              View on PaperProcessor
                            </a>
                          ) : (
                            <a href={absHref} target="_blank" rel="noopener noreferrer" className="text-xs px-2 py-1 rounded border bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600">View on arXiv</a>
                          )}
                          <button
                            onClick={() => handleRemove(it.arxivId)}
                            disabled={removing === it.arxivId}
                            className="text-xs px-2 py-1 rounded border bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
                          >
                            {removing === it.arxivId ? 'Removing...' : 'Remove'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {items && items.length === 0 && (
                  <tr>
                    <td colSpan={3} className="p-4 text-sm text-gray-600 dark:text-gray-300">You have no requests yet.</td>
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
