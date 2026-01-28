"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import type { MinimalPaper } from '../../types/paper';
import { listMinimalPapers } from '../../services/api';

export default function AllPapersPage() {
  const [items, setItems] = useState<MinimalPaper[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        setIsLoading(true);
        setError(null);
        const enriched: MinimalPaper[] = await listMinimalPapers();
        if (isMounted) setItems(enriched);
      } catch (e) {
        if (isMounted) setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        if (isMounted) setIsLoading(false);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-4 flex items-center justify-between">
          <h1 className="text-3xl font-bold">All Papers</h1>
          <button
            onClick={() => { setValue(''); setFormError(null); setOpen(true); }}
            className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700"
          >
            Request a paper
          </button>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">Your daily dose of snackable papers.</p>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="text-gray-600 dark:text-gray-300">Loading…</div>
        ) : items.length === 0 ? (
          <div className="text-gray-600 dark:text-gray-300">No papers found. Add JSON files to <span className="font-mono">data/paperjsons/</span>.</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(({ paperUuid, title, authors, thumbnailUrl, slug }) => (
              <Link key={paperUuid} href={slug ? `/paper/${encodeURIComponent(slug)}` : '#'} className={`group ${slug ? '' : 'pointer-events-none opacity-60'}`}>
                <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden shadow-sm h-full">
                  <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 flex items-center justify-center overflow-hidden">
                    {thumbnailUrl ? (
                      <img src={thumbnailUrl} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="text-gray-400 text-sm">No thumbnail</div>
                    )}
                  </div>
                  <div className="p-3">
                    <div className="font-semibold text-gray-900 dark:text-gray-100 group-hover:underline break-words line-clamp-3">{title || paperUuid + '.json'}</div>
                    {authors && (
                      <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 break-words line-clamp-3">{authors}</div>
                    )}
                    {!slug && (
                      <div className="text-xs text-gray-400 mt-2">No slug yet</div>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}

        {open && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-lg bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 p-4 shadow-xl">
              <h2 className="text-lg font-semibold mb-2">Enter arXiv URL or ID</h2>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const v = (value || '').trim();
                  if (!v) {
                    setFormError('Please enter an arXiv URL or identifier');
                    return;
                  }
                  setFormError(null);
                  setOpen(false);
                  // Extract base arXiv id: support full abs/pdf URLs, arXiv: prefix, version suffix, and .pdf
                  let id = v;
                  try {
                    // If URL, take last path segment after /abs/ or /pdf/
                    const m = id.match(/https?:\/\/[^/]+\/(abs|pdf)\/([^?#]+)/i);
                    if (m) {
                      id = m[2];
                    }
                    // Drop .pdf suffix if present
                    id = id.replace(/\.pdf$/i, '');
                    // Drop arXiv: prefix
                    id = id.replace(/^arxiv:/i, '');
                    // Drop version suffix like v2
                    id = id.replace(/v\d+$/i, '');
                    id = id.trim();
                  } catch {}
                  router.push(`/checkpaper/${id}`);
                }}
                className="space-y-3"
              >
                <input
                  autoFocus
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  placeholder="e.g., https://arxiv.org/abs/2507.12345 or 2507.12345"
                  className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                {formError && (
                  <div className="text-xs text-red-600 dark:text-red-400">{formError}</div>
                )}
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="px-3 py-1.5 text-sm rounded-md border bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-3 py-1.5 text-sm rounded-md bg-blue-600 text-white hover:bg-blue-700"
                  >
                    Continue
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}


