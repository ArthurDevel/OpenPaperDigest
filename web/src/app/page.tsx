/**
 * Homepage - Papers Feed
 *
 * Main landing page displaying an infinite scroll feed of research papers.
 * Responsibilities:
 * - Load and display papers in a paginated feed
 * - Handle paper expansion to show summaries
 * - Manage infinite scroll with intersection observer
 * - Preserve scroll position when expanding/collapsing papers
 */

"use client";

import React, { useEffect, useState, useRef, useCallback, useLayoutEffect } from 'react';
import type { MinimalPaperItem } from '../types/paper';
import { listMinimalPapersPaginated, fetchPaperSummary, PaperSummaryResponse } from '../services/api';
import PaperCard from '../components/PaperCard';
import { usePaperImpression, trackPaperOpened } from '../hooks/useUmamiTracking';
import NewPapersBanner from '../components/NewPapersBanner';

// ============================================================================
// CONSTANTS
// ============================================================================

const ITEMS_PER_PAGE = 20;

// ============================================================================
// HELPER COMPONENT
// ============================================================================

/**
 * A wrapper for PaperCard that adds impression tracking.
 */
const PaperCardWithImpressionTracking = ({
  paper,
  isExpanded,
  isLoadingSummary,
  summary,
  onToggleExpand,
  onLoadSummary,
}: {
  paper: MinimalPaperItem;
  isExpanded: boolean;
  isLoadingSummary: boolean;
  summary?: PaperSummaryResponse;
  onToggleExpand: (paperUuid: string) => void;
  onLoadSummary?: (paperUuid: string) => void;
}) => {
  const impressionRef = usePaperImpression(paper.paperUuid, true);

  return (
    <PaperCard
      ref={impressionRef}
      paper={paper}
      isExpanded={isExpanded}
      isLoadingSummary={isLoadingSummary}
      summary={summary}
      onToggleExpand={onToggleExpand}
      onLoadSummary={onLoadSummary}
    />
  );
};

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export default function ScrollingPapersPage() {
  const [papers, setPapers] = useState<MinimalPaperItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [hasMore, setHasMore] = useState<boolean>(true);
  const [expandedPaperIds, setExpandedPaperIds] = useState<Set<string>>(new Set());
  const [paperSummaries, setPaperSummaries] = useState<Map<string, PaperSummaryResponse>>(new Map());
  const [loadingSummaries, setLoadingSummaries] = useState<Set<string>>(new Set());
  const [pendingScrollAdjustment, setPendingScrollAdjustment] = useState<{ elementId: string; offsetFromTop: number } | null>(null);

  const observerTarget = useRef<HTMLDivElement>(null);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Loads a specific page of papers from the API
   * @param page - The page number to load
   */
  const loadPage = useCallback(async (page: number): Promise<void> => {
    if (isLoading) return;

    try {
      setIsLoading(true);
      setError(null);
      const result = await listMinimalPapersPaginated(page, ITEMS_PER_PAGE);

      setPapers(prev => {
        // Avoid duplicates
        const existingIds = new Set(prev.map(p => p.paperUuid));
        const newPapers = result.items.filter(p => !existingIds.has(p.paperUuid));

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
  }, [isLoading, paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

  /**
   * Toggles the expanded state of a paper
   * @param paperUuid - The UUID of the paper to expand or collapse
   */
  const toggleExpanded = useCallback((paperUuid: string): void => {
    const isCurrentlyExpanded = expandedPaperIds.has(paperUuid);

    if (isCurrentlyExpanded) {
      // Just collapse this one
      setExpandedPaperIds(prev => {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      });
    } else {
      // Track the "paper opened" event
      trackPaperOpened(paperUuid);

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

  /**
   * Loads the summary for a specific paper
   * @param paperUuid - The UUID of the paper to load the summary for
   */
  const loadPaperSummary = async (paperUuid: string): Promise<void> => {
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

  // ============================================================================
  // EFFECTS
  // ============================================================================

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

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <NewPapersBanner />
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
            const isExpanded = expandedPaperIds.has(paper.paperUuid);
            const summary = paperSummaries.get(paper.paperUuid);
            const isLoadingSummary = loadingSummaries.has(paper.paperUuid);

            return (
              <PaperCardWithImpressionTracking
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
            No papers found
          </div>
        )}
      </div>
    </main>
  );
}
