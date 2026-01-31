"use client";

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { checkArxiv, getArxivMetadata, type ArxivMetadata } from '../../../services/api';
import { ExternalLink } from 'lucide-react';
import RequestPaperButton from '../../../components/RequestPaperButton';

export default function CheckPaperPage() {
  const params = useParams<{ arxivId: string }>();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState<boolean>(true);
  const [metadata, setMetadata] = useState<ArxivMetadata | null>(null);

  useEffect(() => {
    const arxivId = (params?.arxivId || '').trim();
    if (!arxivId) {
      setError('Missing arXiv ID');
      setChecking(false);
      return;
    }
    (async () => {
      try {
        setChecking(true);
        setError(null);
        setMetadata(null);
        const res = await checkArxiv(arxivId);
        if (res.exists && res.viewerUrl) {
          router.replace(res.viewerUrl);
          return;
        }
        const meta = await getArxivMetadata(arxivId);
        setMetadata(meta);
      } catch (e: any) {
        setError(e?.message || 'Failed to check paper');
      } finally {
        setChecking(false);
      }
    })();
  }, [params, router]);

  const arxivId = (params?.arxivId || '').trim();
  const absUrl = metadata?.arxivId ? `https://arxiv.org/abs/${encodeURIComponent(metadata.arxivId)}` : (arxivId ? `https://arxiv.org/abs/${encodeURIComponent(arxivId)}` : '#');


  return (
    <main className="w-full">
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">{error}</div>
        )}
        {checking ? (
          <div className="text-gray-600 dark:text-gray-300">Checking if this paper is available…</div>
        ) : metadata ? (
          <div className="flex flex-col space-y-6">
            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <div className="min-w-0 flex-1 overflow-hidden break-words">
                <h1 className="text-3xl font-bold mb-1 break-words whitespace-normal">{metadata.title}</h1>
                <p className="text-sm text-gray-700 dark:text-gray-300 mb-1 break-words whitespace-normal">
                  {metadata.authors.map(a => a.name).join(', ')}
                </p>
                <a
                  href={absUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
                  title="Open on arXiv"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  Open on arXiv
                </a>
              </div>
            </div>

            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <h2 className="text-xl font-semibold mb-2">This paper is not yet available on Open Paper Digest</h2>
              <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">Request this paper for processing using the button below</p>
              <RequestPaperButton arxivId={(metadata?.arxivId || arxivId)} />
            </div>

            <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden p-4">
              <h2 className="text-xl font-semibold mb-2">Abstract</h2>
              <div className="prose dark:prose-invert max-w-none text-sm">
                <p>{metadata.summary}</p>
              </div>
            </div>
          </div>
        ) : (
          !error && (
            <div className="text-gray-600 dark:text-gray-300">No information found for this paper.</div>
          )
        )}
      </div>
    </main>
  );
}


