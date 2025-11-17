'use client';

import React, { useEffect, useState } from 'react';
import { authClient } from '../../../services/auth';
import { getMyUserList, type UserListItem, removePaperFromUserList } from '../../../services/users';
import { Loader } from 'lucide-react';

export default function UserListPage() {
  const { data: session } = authClient.useSession();
  const [items, setItems] = useState<UserListItem[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [removing, setRemoving] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      if (!session?.user?.id) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const list = await getMyUserList(session.user.id);
        setItems(list);
      } catch (e: any) {
        setError(e?.message || 'Failed to load your list');
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [session?.user?.id]);

  const handleRemove = async (paper_uuid: string) => {
    if (!session?.user?.id) return;
    try {
      setRemoving(paper_uuid);
      await removePaperFromUserList(paper_uuid, session.user.id);
      setItems((prev) => (prev || []).filter((it) => it.paper_uuid !== paper_uuid));
    } catch (e: any) {
      alert(e?.message || 'Failed to remove');
    } finally {
      setRemoving(null);
    }
  };

  if (!session?.user?.id) {
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
            <Loader className="animate-spin w-4 h-4 mr-2" /> Loading…
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
                  const href = `/paper/${encodeURIComponent(it.slug || it.paper_uuid)}`;
                  const added = it.created_at ? new Date(it.created_at) : null;
                  const addedStr = added ? added.toLocaleDateString() + ' ' + added.toLocaleTimeString() : '-';
                  return (
                    <tr key={it.paper_uuid} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="p-2 align-top">
                        {it.thumbnail_data_url ? (
                          <a href={href}>
                            <img src={it.thumbnail_data_url} alt="" className="w-20 h-14 object-cover rounded" />
                          </a>
                        ) : (
                          <div className="w-20 h-14 bg-gray-200 dark:bg-gray-700 rounded" />
                        )}
                      </td>
                      <td className="p-2 align-top">
                        <a href={href} className="font-medium hover:underline">{it.title || it.paper_uuid}</a>
                        {it.authors && (
                          <div className="text-xs text-gray-600 dark:text-gray-400 truncate">{it.authors}</div>
                        )}
                      </td>
                      <td className="p-2 align-top whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">{addedStr}</td>
                      <td className="p-2 align-top">
                        <div className="flex gap-2">
                          <a href={href} className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600">View</a>
                          <button
                            onClick={() => handleRemove(it.paper_uuid)}
                            disabled={removing === it.paper_uuid}
                            className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600"
                          >
                            {removing === it.paper_uuid ? 'Removing…' : 'Remove'}
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


