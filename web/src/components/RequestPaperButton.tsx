'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader } from 'lucide-react';
import { useSession } from '@/services/auth';
import { setPostLoginCookie } from '@/lib/postLogin';
import { addUserRequest, doesUserRequestExist, removeUserRequest } from '@/services/requests';

type RequestPaperButtonProps = {
  arxivId: string;
};

/**
 * Button to request processing for an arXiv paper.
 * Unauthenticated users are redirected to login with a post-login action set.
 * @param arxivId - arXiv ID of the paper to request
 * @returns Request paper button component
 */
export default function RequestPaperButton({ arxivId }: RequestPaperButtonProps) {
  const { user } = useSession();
  const router = useRouter();

  const [pending, setPending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isRequested, setIsRequested] = useState<boolean>(false);

  // Check if user has already requested this paper
  useEffect(() => {
    const run = async () => {
      if (!user?.id || !arxivId) return;
      try {
        const exists = await doesUserRequestExist(arxivId);
        setIsRequested(Boolean(exists));
      } catch {
        // Ignore errors when checking request status
      }
    };
    run();
  }, [user?.id, arxivId]);

  /**
   * Handles button click - adds/removes request or redirects to login
   */
  const handleClick = async (): Promise<void> => {
    setError(null);

    // If not logged in, set post-login action and redirect to login
    if (!user?.id) {
      setPostLoginCookie({
        method: 'POST',
        url: `/api/users/me/requests/${encodeURIComponent(arxivId)}`,
        redirect: window.location.pathname,
      });
      router.push('/login');
      return;
    }

    // Toggle request
    try {
      setPending(true);
      if (isRequested) {
        await removeUserRequest(arxivId);
        setIsRequested(false);
      } else {
        await addUserRequest(arxivId);
        setIsRequested(true);
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : 'Failed to request';
      setError(message);
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleClick}
        disabled={pending}
        className={`px-3 py-1.5 text-sm rounded-md border ${isRequested ? 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-600/60' : 'bg-indigo-600 text-white hover:bg-indigo-700 border-transparent'}`}
        title={isRequested ? 'Click to remove your request' : 'Request processing for this paper'}
      >
        {pending ? (
          <span className="inline-flex items-center gap-2"><Loader className="animate-spin w-4 h-4" /> Processing...</span>
        ) : isRequested ? 'Requested' : 'Request Processing'}
      </button>
      {error && (
        <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
      )}
    </div>
  );
}
