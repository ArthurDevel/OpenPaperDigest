'use client';

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Loader, Lock } from 'lucide-react';
import { authClient } from '../services/auth';
import { addPaperToUserList, isPaperInUserList, removePaperFromUserList } from '../services/users';
import { setPostLoginCookie } from '@/lib/postLogin';
import { sendAddToListMagicLink } from '@/lib/magicLink';

type AddToListButtonProps = {
  paperId: string;
  paperTitle?: string;
  redirectTo?: string;
};

export default function AddToListButton({ paperId, paperTitle, redirectTo }: AddToListButtonProps) {
  const { data: session } = authClient.useSession();
  const pathname = usePathname();

  const [isInList, setIsInList] = useState<boolean>(false);
  const [checkPending, setCheckPending] = useState<boolean>(false);
  const [addPending, setAddPending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showEmailForm, setShowEmailForm] = useState<boolean>(false);
  const [email, setEmail] = useState<string>('');
  const [emailSent, setEmailSent] = useState<boolean>(false);

  useEffect(() => {
    const run = async () => {
      if (!paperId || !session?.user?.id) return;
      try {
        setCheckPending(true);
        const exists = await isPaperInUserList(paperId, session.user.id);
        setIsInList(Boolean(exists));
      } catch {
        // ignore
      } finally {
        setCheckPending(false);
      }
    };
    run();
  }, [paperId, session?.user?.id]);

  const handleAddClick = async () => {
    setError(null);
    if (!paperId) {
      setError('Missing paper id');
      return;
    }
    if (!session?.user?.id) {
      setShowEmailForm((v) => !v);
      return;
    }
    try {
      setAddPending(true);
      if (isInList) {
        await removePaperFromUserList(paperId, session.user.id);
        setIsInList(false);
      } else {
        await addPaperToUserList(paperId, session.user.id);
        setIsInList(true);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to update list');
    } finally {
      setAddPending(false);
    }
  };

  const handleSendMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      if (!paperId) throw new Error('Missing paper id');
      const redirect = redirectTo || pathname || '/';
      setPostLoginCookie({
        method: 'POST',
        url: `/api/users/me/list/${encodeURIComponent(paperId)}`,
        redirect,
      });
      await sendAddToListMagicLink(email, paperTitle || '');
      setShowEmailForm(false);
      setEmailSent(true);
    } catch (e: any) {
      setError(e?.message || 'Failed to send magic link');
    }
  };

  const disabled = addPending || checkPending || !paperId;
  const title = !paperId
    ? 'Missing paper id'
    : isInList
      ? 'Click to remove from your list'
      : 'Add this paper to your list';

  // Unauthenticated flow: show form in place of the button when toggled, or a success message after sending
  if (!session?.user?.id && showEmailForm) {
    return (
      <div className="w-full max-w-md bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-4 flex flex-col gap-3">
        <div className="text-sm text-gray-700 dark:text-gray-200">
          Log in using our one-click system to add this paper to your list
        </div>
        <form onSubmit={handleSendMagicLink} className="flex items-center gap-2">
          <input
            type="email"
            required
            placeholder="your@email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="appearance-none block w-56 px-3 py-1.5 border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 text-sm"
          />
          <button
            type="submit"
            className="px-3 py-1.5 text-sm rounded-md border bg-indigo-600 text-white hover:bg-indigo-700 border-transparent"
          >
            log in and add to list
          </button>
        </form>
        {error && (
          <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
        )}
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
          <Lock className="w-3.5 h-3.5" /> BetterAuth handles authentication securely using MagicLink.
        </div>
      </div>
    );
  }

  if (!session?.user?.id && emailSent) {
    return (
      <div className="w-full max-w-md bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-4 flex flex-col gap-3">
        <div className="text-sm text-gray-700 dark:text-gray-200">
          Click the link in your inbox to confirm your log in and add this paper to your list. Not seeing the email? Please wait a minute and check your spam folder.
        </div>
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
          <Lock className="w-3.5 h-3.5" /> BetterAuth handles authentication securely using MagicLink.
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleAddClick}
        disabled={disabled}
        className={`px-3 py-1.5 text-sm rounded-md border ${isInList ? 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-600/60' : 'bg-indigo-600 text-white hover:bg-indigo-700 border-transparent'}`}
        title={title}
      >
        {addPending || checkPending ? (
          <span className="inline-flex items-center gap-2"><Loader className="animate-spin w-4 h-4" /> Processing…</span>
        ) : isInList ? 'In your list' : '+ Add to list'}
      </button>

      {error && session?.user?.id && (
        <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
      )}
    </div>
  );
}


