"use client";

import React, { useEffect, useState, useRef, useCallback } from 'react';
import type { MinimalPaperItem, PaperSummary } from '../../../types/paper';
import { listMinimalPapersPaginated } from '../../../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { ExternalLink, Share, Check } from 'lucide-react';
import AddToListButtonMobile from '../../../components/AddToListButtonMobile';
import CopyMarkdownButton from '../../../components/CopyMarkdownButton';
import PaperCard from '../../../components/PaperCard';

const ITEMS_PER_PAGE = 20;

// Preprocess backticked math expressions
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

interface SharedPaperClientProps {
  initialPaperData: PaperSummary;
  slug: string;
}

export default function SharedPaperClient({ initialPaperData, slug }: SharedPaperClientProps) {
  const [papers, setPapers] = useState<MinimalPaperItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [expandedPaperIds, setExpandedPaperIds] = useState<Set<string>>(new Set());
  const [paperSummaries, setPaperSummaries] = useState<Map<string, PaperSummary>>(new Map());
  const [loadingSummaries, setLoadingSummaries] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);

  const observerTarget = useRef<HTMLDivElement>(null);

  // Load papers from a specific page, excluding the featured paper
  const loadPage = useCallback(async (page: number) => {
    if (isLoading) return;

    try {
      setIsLoading(true);
      setError(null);
      const result = await listMinimalPapersPaginated(page, ITEMS_PER_PAGE);

      setPapers(prev => {
        // Avoid duplicates and exclude the featured paper
        const existingIds = new Set(prev.map(p => p.paperUuid));
        const newPapers = result.items.filter(
          p => !existingIds.has(p.paperUuid) && p.paperUuid !== initialPaperData.paperId
        );

        // Load summaries for new papers
        newPapers.forEach(paper => {
          if (!paperSummaries.has(paper.paperUuid) && !loadingSummaries.has(paper.paperUuid)) {
            loadPaperSummary(paper.paperUuid);
          }
        });

        return [...prev, ...newPapers];
      });

      setHasMore(result.hasMore);
      setCurrentPage(page);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, initialPaperData.paperId, paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load initial page
  useEffect(() => {
    loadPage(1);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Infinite scroll observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting && hasMore && !isLoading) {
          loadPage(currentPage + 1);
        }
      },
      { threshold: 1.0 }
    );

    const currentTarget = observerTarget.current;
    if (currentTarget) {
      observer.observe(currentTarget);
    }

    return () => {
      if (currentTarget) {
        observer.unobserve(currentTarget);
      }
    };
  }, [hasMore, isLoading, currentPage, loadPage]);

  // Toggle paper expansion
  const toggleExpanded = useCallback((paperUuid: string) => {
    setExpandedPaperIds(prev => {
      const next = new Set(prev);
      if (next.has(paperUuid)) {
        next.delete(paperUuid);
      } else {
        next.clear();
        next.add(paperUuid);
      }
      return next;
    });
  }, []);

  // Load paper summary
  const loadPaperSummary = async (paperUuid: string) => {
    if (paperSummaries.has(paperUuid) || loadingSummaries.has(paperUuid)) return;

    setLoadingSummaries(prev => new Set(prev).add(paperUuid));

    try {
      const response = await fetch(`/api/papers/${paperUuid}/summary`);
      if (!response.ok) throw new Error('Failed to load summary');
      const summary = await response.json();
      setPaperSummaries(prev => new Map(prev).set(paperUuid, summary));
    } catch (e) {
      console.error('Failed to load summary:', e);
    } finally {
      setLoadingSummaries(prev => {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      });
    }
  };

  // Handle share button click
  const handleShare = async () => {
    const shareUrl = `${window.location.origin}/paper/${slug}`;

    try {
      if (navigator.share) {
        await navigator.share({
          title: initialPaperData.title || 'Research Paper',
          text: `Check out this research paper: ${initialPaperData.title}`,
          url: shareUrl,
        });
      } else {
        // Fallback: copy to clipboard
        await navigator.clipboard.writeText(shareUrl);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }
    } catch (err) {
      console.error('Error sharing:', err);
    }
  };

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        {/* Featured Paper */}
        <div className="mb-8">
          <div className="bg-white dark:bg-gray-800 border-2 border-blue-500 dark:border-blue-400 rounded-lg shadow-lg">
            {/* Header */}
            <div className="bg-blue-50 dark:bg-blue-900/30 px-4 py-2 border-b border-blue-200 dark:border-blue-700">
              <span className="text-xs font-semibold text-blue-700 dark:text-blue-300 uppercase tracking-wide">
                Featured Paper
              </span>
            </div>

            {/* Paper content */}
            <div className="p-4">
              <div className="flex items-start gap-4 mb-4">
                {initialPaperData.thumbnailUrl && (
                  <img
                    src={initialPaperData.thumbnailUrl}
                    alt=""
                    className="w-20 h-20 sm:w-24 sm:h-24 rounded-md object-cover flex-shrink-0"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2 break-words">
                    {initialPaperData.title || 'Untitled'}
                  </h1>
                  {initialPaperData.authors && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                      {initialPaperData.authors}
                    </p>
                  )}
                  {initialPaperData.arxivUrl && (
                    <a
                      href={initialPaperData.arxivUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <ExternalLink className="w-3 h-3" />
                      arXiv
                    </a>
                  )}
                </div>
              </div>

              {/* Five minute summary */}
              {initialPaperData.fiveMinuteSummary && (
                <div className="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                      5-Minute Summary
                    </span>
                  </div>
                  <div className="prose prose-sm dark:prose-invert max-w-none">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm, remarkMath]}
                      rehypePlugins={[rehypeKatex]}
                    >
                      {preprocessBacktickedMath(initialPaperData.fiveMinuteSummary)}
                    </ReactMarkdown>
                  </div>

                  {/* Action buttons - bottom right corner */}
                  <div className="mt-4 flex items-center justify-end gap-2">
                    <CopyMarkdownButton paperUuid={initialPaperData.paperId} fiveMinuteSummary={initialPaperData.fiveMinuteSummary} />
                    <AddToListButtonMobile paperId={initialPaperData.paperId} paperTitle={initialPaperData.title || undefined} />
                    <button
                      onClick={handleShare}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-blue-500 dark:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-blue-600 dark:text-blue-400 text-xs"
                      title="Share this paper"
                      aria-label="Share this paper"
                    >
                      {copied ? (
                        <span className="text-green-600 dark:text-green-400 font-medium">Copied</span>
                      ) : (
                        <>
                          <Share className="w-4 h-4" />
                          <span>Share</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Separator */}
        <div className="mb-6">
          <div className="flex items-center gap-3">
            <div className="flex-1 h-px bg-gray-300 dark:bg-gray-700"></div>
            <span className="text-sm text-gray-500 dark:text-gray-400 font-medium">More Papers</span>
            <div className="flex-1 h-px bg-gray-300 dark:bg-gray-700"></div>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Feed of other papers */}
        <div className="space-y-4">
          {papers.map((paper) => {
            const isExpanded = expandedPaperIds.has(paper.paperUuid);
            const summary = paperSummaries.get(paper.paperUuid);
            const isLoadingSummary = loadingSummaries.has(paper.paperUuid);

            return (
              <PaperCard
                key={paper.paperUuid}
                paper={paper}
                isExpanded={isExpanded}
                isLoadingSummary={isLoadingSummary}
                summary={summary}
                onToggleExpand={toggleExpanded}
                onLoadSummary={loadPaperSummary}
              />
            );
          })}
        </div>

        {/* Loading indicator */}
        {isLoading && (
          <div className="text-center py-8 text-gray-600 dark:text-gray-300">
            Loading more papers...
          </div>
        )}

        {/* Intersection observer target */}
        {hasMore && !isLoading && (
          <div ref={observerTarget} className="h-8" />
        )}

        {/* End of list */}
        {!hasMore && papers.length > 0 && (
          <div className="text-center py-8 text-gray-600 dark:text-gray-400 text-sm">
            You've reached the end of the list
          </div>
        )}

        {/* No papers */}
        {!isLoading && papers.length === 0 && (
          <div className="text-center py-8 text-gray-600 dark:text-gray-300">
            No more papers to show
          </div>
        )}
      </div>
    </main>
  );
}
