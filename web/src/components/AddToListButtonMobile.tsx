'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader, Plus, Check } from 'lucide-react';
import { useSession } from '@/services/auth';
import { addPaperToUserList, isPaperInUserList, removePaperFromUserList } from '@/services/users';
import { setPostLoginCookie } from '@/lib/postLogin';

type AddToListButtonMobileProps = {
  paperId: string;
  redirectTo?: string;
};

/**
 * Mobile-optimized button to add/remove a paper from the user's reading list.
 * Unauthenticated users are redirected to login with a post-login action set.
 * @param paperId - UUID of the paper
 * @param redirectTo - URL to redirect to after login (defaults to current path)
 * @returns Compact add to list button component for mobile
 */
export default function AddToListButtonMobile({ paperId, redirectTo }: AddToListButtonMobileProps) {
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
    <>
      <button
        onClick={handleAddClick}
        disabled={disabled}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md border transition-colors text-xs ${
          isInList
            ? 'bg-green-50 dark:bg-green-900/20 border-green-500 dark:border-green-400 text-green-700 dark:text-green-300'
            : 'border-blue-500 dark:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400'
        }`}
        title={title}
      >
        {addPending || checkPending ? (
          <Loader className="animate-spin w-4 h-4" />
        ) : isInList ? (
          <Check className="w-4 h-4" />
        ) : (
          <Plus className="w-4 h-4" />
        )}
        <span>{isInList ? 'Added' : 'Add to list'}</span>
      </button>

      {/* Error message for authenticated users */}
      {error && user?.id && (
        <div className="absolute top-full mt-2 right-0 p-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded text-xs whitespace-nowrap">
          {error}
        </div>
      )}
    </>
  );
}
