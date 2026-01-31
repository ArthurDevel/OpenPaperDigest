'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader } from 'lucide-react';
import { useSession } from '@/services/auth';
import { addPaperToUserList, isPaperInUserList, removePaperFromUserList } from '@/services/users';
import { setPostLoginCookie } from '@/lib/postLogin';

type AddToListButtonProps = {
  paperId: string;
  redirectTo?: string;
};

/**
 * Button to add/remove a paper from the user's reading list.
 * Unauthenticated users are redirected to login with a post-login action set.
 * @param paperId - UUID of the paper
 * @param redirectTo - URL to redirect to after login (defaults to current path)
 * @returns Add to list button component
 */
export default function AddToListButton({ paperId, redirectTo }: AddToListButtonProps) {
  const { user } = useSession();
  const router = useRouter();

  const [isInList, setIsInList] = useState<boolean>(false);
  const [checkPending, setCheckPending] = useState<boolean>(false);
  const [addPending, setAddPending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Check if paper is already in user's list
  useEffect(() => {
    const run = async () => {
      if (!paperId || !user?.id) return;
      try {
        setCheckPending(true);
        const exists = await isPaperInUserList(paperId);
        setIsInList(Boolean(exists));
      } catch {
        // Ignore errors when checking list status
      } finally {
        setCheckPending(false);
      }
    };
    run();
  }, [paperId, user?.id]);

  /**
   * Handles button click - adds/removes from list or redirects to login
   */
  const handleAddClick = async (): Promise<void> => {
    setError(null);
    if (!paperId) {
      setError('Missing paper id');
      return;
    }

    // If not logged in, set post-login action and redirect to login
    if (!user?.id) {
      setPostLoginCookie({
        method: 'POST',
        url: `/api/users/me/list/${encodeURIComponent(paperId)}`,
        redirect: redirectTo || window.location.pathname,
      });
      router.push('/login');
      return;
    }

    // Toggle list membership
    try {
      setAddPending(true);
      if (isInList) {
        await removePaperFromUserList(paperId);
        setIsInList(false);
      } else {
        await addPaperToUserList(paperId);
        setIsInList(true);
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to update list';
      setError(message);
    } finally {
      setAddPending(false);
    }
  };

  const disabled = addPending || checkPending || !paperId;
  const title = !paperId
    ? 'Missing paper id'
    : isInList
      ? 'Click to remove from your list'
      : 'Add this paper to your list';

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleAddClick}
        disabled={disabled}
        className={`px-3 py-1.5 text-sm rounded-md border ${isInList ? 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-600/60' : 'bg-indigo-600 text-white hover:bg-indigo-700 border-transparent'}`}
        title={title}
      >
        {addPending || checkPending ? (
          <span className="inline-flex items-center gap-2"><Loader className="animate-spin w-4 h-4" /> Processing...</span>
        ) : isInList ? 'In your list' : '+ Add to list'}
      </button>

      {error && user?.id && (
        <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
      )}
    </div>
  );
}
