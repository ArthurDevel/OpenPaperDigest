'use client';

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Loader, Lock, X, Plus, Check } from 'lucide-react';
import { authClient } from '../services/auth';
import { addPaperToUserList, isPaperInUserList, removePaperFromUserList } from '../services/users';
import { setPostLoginCookie } from '@/lib/postLogin';
import { sendAddToListMagicLink } from '@/lib/magicLink';

type AddToListButtonMobileProps = {
  paperId: string;
  paperTitle?: string;
  redirectTo?: string;
};

export default function AddToListButtonMobile({ paperId, paperTitle, redirectTo }: AddToListButtonMobileProps) {
  const { data: session } = authClient.useSession();
  const pathname = usePathname();

  const [isInList, setIsInList] = useState<boolean>(false);
  const [checkPending, setCheckPending] = useState<boolean>(false);
  const [addPending, setAddPending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showPopup, setShowPopup] = useState<boolean>(false);
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
      setShowPopup(true);
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

      {/* Popup Modal */}
      {showPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50" onClick={() => setShowPopup(false)}>
          <div
            className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close button */}
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {emailSent ? 'Check your email' : 'Add to your list'}
              </h3>
              <button
                onClick={() => {
                  setShowPopup(false);
                  setEmailSent(false);
                  setEmail('');
                  setError(null);
                }}
                className="p-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {emailSent ? (
              // Success state
              <div className="space-y-4">
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Click the link in your inbox to confirm your log in and add this paper to your list.
                  Not seeing the email? Please wait a minute and check your spam folder.
                </div>
                <div className="pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  <span>BetterAuth handles authentication securely using MagicLink.</span>
                </div>
              </div>
            ) : (
              // Login form
              <div className="space-y-4">
                <div className="text-sm text-gray-700 dark:text-gray-300">
                  Log in using our one-click system to add this paper to your list
                </div>

                <form onSubmit={handleSendMagicLink} className="space-y-3">
                  <input
                    type="email"
                    required
                    placeholder="your@email.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                  />
                  <button
                    type="submit"
                    className="w-full px-4 py-2 text-sm font-medium rounded-md bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                  >
                    Log in and add to list
                  </button>
                </form>

                {error && (
                  <div className="p-3 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded-md text-sm">
                    {error}
                  </div>
                )}

                <div className="pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  <span>BetterAuth handles authentication securely using MagicLink.</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Error message for authenticated users */}
      {error && session?.user?.id && (
        <div className="absolute top-full mt-2 right-0 p-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 rounded text-xs whitespace-nowrap">
          {error}
        </div>
      )}
    </>
  );
}
