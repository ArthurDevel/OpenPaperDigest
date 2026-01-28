'use client';

import React, { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Loader, Lock } from 'lucide-react';
import { authClient } from '../services/auth';
import { sendRequestPaperMagicLink } from '../authentication/magicLink';
import { setPostLoginCookie } from '../authentication/postLogin';
import { addUserRequest, doesUserRequestExist, removeUserRequest } from '../services/requests';

type RequestPaperButtonProps = {
  arxivId: string;
};

export default function RequestPaperButton({ arxivId }: RequestPaperButtonProps) {
  const { data: session } = authClient.useSession();
  const pathname = usePathname();

  const [pending, setPending] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [showEmailForm, setShowEmailForm] = useState<boolean>(false);
  const [email, setEmail] = useState<string>('');
  const [emailSent, setEmailSent] = useState<boolean>(false);
  const [isRequested, setIsRequested] = useState<boolean>(false);

  useEffect(() => {
    const run = async () => {
      if (!session?.user?.id || !arxivId) return;
      try {
        const exists = await doesUserRequestExist(arxivId, session.user.id);
        setIsRequested(Boolean(exists));
      } catch {
        // ignore
      }
    };
    run();
  }, [session?.user?.id, arxivId]);

  const handleClick = async () => {
    setError(null);
    if (!session?.user?.id) {
      setShowEmailForm(true);
      return;
    }
    try {
      setPending(true);
      if (isRequested) {
        await removeUserRequest(arxivId, session.user.id);
        setIsRequested(false);
      } else {
        await addUserRequest(arxivId, session.user.id);
        setIsRequested(true);
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to request');
    } finally {
      setPending(false);
    }
  };

  const handleSendMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      // Set HTTP post-login cookie so callback can perform the request after login
      setPostLoginCookie({
        method: 'POST',
        url: `/api/users/me/requests/${encodeURIComponent(arxivId)}`,
        redirect: pathname || '/donate',
      });
      await sendRequestPaperMagicLink(email, `https://arxiv.org/abs/${encodeURIComponent(arxivId)}`);
      setShowEmailForm(false);
      setEmailSent(true);
    } catch (e: any) {
      setError(e?.message || 'Failed to send magic link');
    }
  };

  // Unauthenticated flow: show form
  if (!session?.user?.id && showEmailForm) {
    return (
      <div className="w-full max-w-md bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-4 flex flex-col gap-3">
        <div className="text-sm text-gray-700 dark:text-gray-200">
          Log in and get notified when this paper becomes available
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
            Get Notified
          </button>
        </form>
        {error && (
          <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
        )}
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
          <Lock className="w-3.5 h-3.5" /> MagicLink securely handled by BetterAuth
        </div>
      </div>
    );
  }

  // Unauthenticated: after email sent, show success with security note
  if (!session?.user?.id && emailSent) {
    return (
      <div className="w-full max-w-md bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-4 flex flex-col gap-3">
        <div className="text-sm text-gray-700 dark:text-gray-200">
          Click the link in your inbox to confirm your notification
        </div>
        <div className="pt-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
          <Lock className="w-3.5 h-3.5" /> MagicLink securely handled by BetterAuth
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleClick}
        disabled={pending}
        className={`px-3 py-1.5 text-sm rounded-md border ${isRequested ? 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 hover:bg-gray-600/60' : 'bg-indigo-600 text-white hover:bg-indigo-700 border-transparent'}`}
        title={isRequested ? 'Click to remove your request' : 'Request processing for this paper'}
      >
        {pending ? (
          <span className="inline-flex items-center gap-2"><Loader className="animate-spin w-4 h-4" /> Processing…</span>
        ) : isRequested ? 'Requested' : 'Request Processing'}
      </button>
      {error && (
        <div className="p-2 bg-red-100 border border-red-300 text-red-700 rounded text-xs">{error}</div>
      )}
    </div>
  );
}


