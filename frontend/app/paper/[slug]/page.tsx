"use client";

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { Paper } from '../../../types/paper';
import AddToListButton from '../../../components/AddToListButton';
import CopyMarkdownButton from '../../../components/CopyMarkdownButton';
import { Loader, ExternalLink } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

// Minimal approach: convert backticked segments that look like TeX into $...$
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

export default function PaperPage() {
  const params = useParams<{ slug: string }>();
  const [paperData, setPaperData] = useState<Paper | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [similarItems, setSimilarItems] = useState<Array<{ key: string; title: string | null; authors: string | null; thumbnail_url: string | null; slug: string | null }>>([]);

  useEffect(() => {
    const slug = params?.slug || '';
    let cancelled = false;
    (async () => {
      try {
        if (!slug) throw new Error('Missing slug');
        // Resolve slug to paper_uuid
        const res = await fetch(`/api/papers/slug/${encodeURIComponent(slug)}`, { cache: 'no-store' });
        if (res.status === 404) {
          window.location.replace('/404');
          return;
        }
        if (!res.ok) {
          const text = await res.text().catch(() => '');
          throw new Error(`Resolve failed (${res.status}) ${text}`);
        }
        const json = await res.json();
        if (json?.tombstone) {
          window.location.replace('/410');
          return;
        }
        const uuid: string | undefined = json?.paper_uuid;
        if (!uuid) throw new Error('Paper not found');

        setIsLoading(true);
        // Fetch paper data using summary endpoint (lightweight, no page images)
        const paperRes = await fetch(`/api/papers/${uuid}/summary`, { cache: 'no-store' });
        if (!paperRes.ok) throw new Error(`Failed to load paper: ${paperRes.status}`);
        const paperJson = await paperRes.json();
        if (cancelled) return;

        setPaperData({
          paper_id: paperJson.paper_id,
          title: paperJson.title,
          authors: paperJson.authors,
          arxiv_url: paperJson.arxiv_url,
          five_minute_summary: paperJson.five_minute_summary,
          thumbnail_url: paperJson.thumbnail_url,
        });
      } catch (err) {
        console.error('Error loading paper:', err);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [params?.slug]);

  useEffect(() => {
    // Similar papers functionality disabled for now
    if (!paperData) return;
    setSimilarItems([]);
  }, [paperData]);

  return (
    <div className="flex items-start gap-4 p-2 sm:p-4 min-h-0 text-gray-900 dark:text-gray-100">
      {/* Content - Now full width without sidebars */}
      <main className="flex-1 max-w-4xl mx-auto w-full p-2 sm:p-4 flex flex-col">
        {paperData ? (
          <>
            <div className="mb-4 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md p-3 sm:p-4">
              <div className="flex flex-col sm:flex-row items-start gap-3 sm:gap-4 max-w-full">
                {paperData.thumbnail_url && (
                  <img
                    src={paperData.thumbnail_url}
                    alt="Paper thumbnail"
                    className="w-20 h-20 sm:w-24 sm:h-24 rounded-md object-cover flex-shrink-0 mx-auto sm:mx-0"
                  />
                )}
                <div className="min-w-0 flex-1 break-words text-center sm:text-left">
                  <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold mb-1 break-words whitespace-normal leading-tight">{paperData.title || 'Untitled'}</h1>
                  {paperData.authors && (
                    <p className="text-sm text-gray-700 dark:text-gray-300 mb-1 break-words whitespace-normal">{paperData.authors}</p>
                  )}

                  {paperData.arxiv_url && (
                    <a
                      href={paperData.arxiv_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="mt-2 inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline"
                      title="Open on arXiv"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      Open on arXiv
                    </a>
                  )}
                  <div className="mt-3 flex flex-col sm:flex-row items-start gap-3">
                    <AddToListButton paperId={paperData.paper_id} paperTitle={paperData.title || undefined} />
                    <CopyMarkdownButton paperUuid={paperData.paper_id} fiveMinuteSummary={paperData.five_minute_summary} />
                  </div>

                </div>
              </div>
            </div>

            {/* 5-Minute Summary */}
            {paperData.five_minute_summary && (
              <div className="mb-6 sm:mb-8 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg shadow-md overflow-hidden">
                <div className="p-3 sm:p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <h2 className="text-lg font-semibold text-blue-900 dark:text-blue-100">
                      5-Minute Summary
                    </h2>
                    <span className="text-xs text-blue-600 dark:text-blue-400 bg-blue-100 dark:bg-blue-900/50 px-2 py-1 rounded-full">
                      ⚡ Quick read
                    </span>
                  </div>
                  <div className="prose dark:prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[[rehypeKatex, { strict: false, throwOnError: false }]]}
                    >
                      {preprocessBacktickedMath(paperData.five_minute_summary)}
                    </ReactMarkdown>
                  </div>
                </div>
              </div>
            )}

            {/* Similar Papers */}
            {similarItems.length > 0 && (
              <div className="mb-6 sm:mb-8 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-md overflow-hidden">
                <div className="p-3 sm:p-4">
                  <h2 className="text-xl font-semibold mb-4 text-gray-900 dark:text-gray-100">Similar papers</h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {similarItems.map(({ key, title, authors, thumbnail_url, slug }) => {
                      const target = slug || key;
                      return (
                        <a
                          key={key}
                          href={`/paper/${encodeURIComponent(target)}`}
                          className="block w-full text-left p-3 rounded-md transition-colors bg-white dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600"
                          title={`Open ${title || key}`}
                          aria-label={`Open ${title || key}`}
                        >
                          <div className="flex items-start gap-3">
                            <div className="w-16 h-16 bg-gray-200 dark:bg-gray-600 rounded-md flex-shrink-0 overflow-hidden">
                              {thumbnail_url && (
                                <img src={thumbnail_url} alt="" className="w-16 h-16 object-cover" />
                              )}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-2">{title || key + '.json'}</div>
                              {authors && (
                                <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-1">{authors}</div>
                              )}
                            </div>
                          </div>
                        </a>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          isLoading ? (
            <div className="flex items-center justify-center h-full text-gray-500 dark:text-gray-400">
              <div className="flex flex-col items-center">
                <Loader className="animate-spin w-10 h-10 mb-3" />
                <p>Loading paper...</p>
              </div>
            </div>
          ) : null
        )}
    </main>
    </div>
  );
}
