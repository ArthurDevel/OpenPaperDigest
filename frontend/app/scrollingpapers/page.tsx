"use client";

import React, { useEffect, useState, useRef, useCallback, useLayoutEffect } from 'react';
import type { MinimalPaperItem, Paper } from '../../types/paper';
import { listMinimalPapersPaginated, fetchPaperSummary } from '../../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

const ITEMS_PER_PAGE = 20;

// Preprocess backticked math expressions
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

export default function ScrollingPapersPage() {
  const [papers, setPapers] = useState<MinimalPaperItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [expandedPaperIds, setExpandedPaperIds] = useState<Set<string>>(new Set());
  const [paperSummaries, setPaperSummaries] = useState<Map<string, Paper>>(new Map());
  const [loadingSummaries, setLoadingSummaries] = useState<Set<string>>(new Set());
  const [pendingScrollAdjustment, setPendingScrollAdjustment] = useState<{ elementId: string; offsetFromTop: number } | null>(null);

  const observerTarget = useRef<HTMLDivElement>(null);

  // Load papers from a specific page
  const loadPage = useCallback(async (page: number) => {
    if (isLoading) return;

    try {
      setIsLoading(true);
      setError(null);
      const result = await listMinimalPapersPaginated(page, ITEMS_PER_PAGE);

      setPapers(prev => {
        // Avoid duplicates
        const existingIds = new Set(prev.map(p => p.paper_uuid));
        const newPapers = result.items.filter(p => !existingIds.has(p.paper_uuid));

        // Load summaries for new papers
        newPapers.forEach(paper => {
          if (!paperSummaries.has(paper.paper_uuid) && !loadingSummaries.has(paper.paper_uuid)) {
            loadPaperSummary(paper.paper_uuid);
          }
        });

        return [...prev, ...newPapers];
      });

      setHasMore(result.has_more);
      setCurrentPage(page);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Restore scroll position after DOM update
  useLayoutEffect(() => {
    if (pendingScrollAdjustment) {
      const element = document.getElementById(pendingScrollAdjustment.elementId);
      if (element) {
        const currentOffsetFromTop = element.getBoundingClientRect().top;
        const scrollAdjustment = currentOffsetFromTop - pendingScrollAdjustment.offsetFromTop;
        window.scrollBy(0, scrollAdjustment);
      }
      setPendingScrollAdjustment(null);
    }
  }, [pendingScrollAdjustment]);

  // Toggle paper expansion
  const toggleExpanded = useCallback((paperUuid: string) => {
    const isCurrentlyExpanded = expandedPaperIds.has(paperUuid);

    if (isCurrentlyExpanded) {
      // Just collapse this one
      setExpandedPaperIds(prev => {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      });
    } else {
      // Expanding a new one - need to handle scroll preservation
      const previouslyExpanded = Array.from(expandedPaperIds)[0];

      if (previouslyExpanded) {
        // Measure the clicked element's position before state change
        const clickedElement = document.getElementById(`paper-${paperUuid}`);
        if (clickedElement) {
          const offsetFromTop = clickedElement.getBoundingClientRect().top;
          setPendingScrollAdjustment({ elementId: `paper-${paperUuid}`, offsetFromTop });
        }
      }

      // Collapse previous and expand new one
      setExpandedPaperIds(new Set([paperUuid]));

      // Load summary if not already loaded
      if (!paperSummaries.has(paperUuid) && !loadingSummaries.has(paperUuid)) {
        loadPaperSummary(paperUuid);
      }
    }
  }, [expandedPaperIds, paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load paper summary
  const loadPaperSummary = async (paperUuid: string) => {
    setLoadingSummaries(prev => new Set(prev).add(paperUuid));

    try {
      const summary = await fetchPaperSummary(paperUuid);
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

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <div className="mb-4">
          <h1 className="text-3xl font-bold">Papers Feed</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
            Scroll through papers and click to expand summaries
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-4">
          {papers.map((paper) => {
            const isExpanded = expandedPaperIds.has(paper.paper_uuid);
            const summary = paperSummaries.get(paper.paper_uuid);
            const isLoadingSummary = loadingSummaries.has(paper.paper_uuid);

            return (
              <div
                key={paper.paper_uuid}
                id={`paper-${paper.paper_uuid}`}
                className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden shadow-sm transition-all"
              >
                {/* Title and Authors */}
                <div className="p-4 pb-3">
                  <h2 className="font-semibold text-lg text-gray-900 dark:text-gray-100 line-clamp-3">
                    {paper.title || 'Untitled'}
                  </h2>
                  {paper.authors && (
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 line-clamp-2">
                      {paper.authors}
                    </p>
                  )}
                </div>

                {/* Thumbnail - always clickable */}
                <button
                  onClick={() => toggleExpanded(paper.paper_uuid)}
                  className="w-full text-left"
                >
                  <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 overflow-hidden hover:opacity-95 transition-opacity">
                    {paper.thumbnail_url ? (
                      <img
                        src={paper.thumbnail_url}
                        alt=""
                        className="w-full h-full object-cover object-top"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
                        No thumbnail
                      </div>
                    )}
                  </div>
                </button>

                {/* Summary Preview or Expanded Content */}
                {isLoadingSummary ? (
                  <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3">
                    <div className="text-gray-600 dark:text-gray-400 text-sm">
                      Loading summary...
                    </div>
                  </div>
                ) : summary?.five_minute_summary ? (
                  isExpanded ? (
                    // Fully expanded
                    <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900/50">
                      <div className="mb-3">
                        <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                          5-Minute Summary
                        </span>
                      </div>
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm, remarkMath]}
                          rehypePlugins={[rehypeKatex]}
                        >
                          {preprocessBacktickedMath(summary.five_minute_summary)}
                        </ReactMarkdown>
                      </div>
                      <button
                        onClick={() => toggleExpanded(paper.paper_uuid)}
                        className="mt-4 text-sm text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        Show less
                      </button>
                    </div>
                  ) : (
                    // Preview with fade-out
                    <button
                      onClick={() => toggleExpanded(paper.paper_uuid)}
                      className="w-full text-left border-t border-gray-200 dark:border-gray-700 px-4 pb-4 pt-3 relative group"
                    >
                      <div className="relative overflow-hidden" style={{ maxHeight: '10rem' }}>
                        <div className="prose prose-sm dark:prose-invert max-w-none text-gray-700 dark:text-gray-300">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm, remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                          >
                            {preprocessBacktickedMath(summary.five_minute_summary)}
                          </ReactMarkdown>
                        </div>
                        {/* Fade overlay */}
                        <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-white dark:from-gray-800 to-transparent pointer-events-none group-hover:from-gray-50 dark:group-hover:from-gray-750 transition-colors" />
                      </div>
                      <div className="mt-2 text-xs text-blue-600 dark:text-blue-400 group-hover:underline">
                        Click to read more
                      </div>
                    </button>
                  )
                ) : null}
              </div>
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
            No papers found
          </div>
        )}
      </div>
    </main>
  );
}
