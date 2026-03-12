/**
 * Homepage - Papers Feed
 *
 * Main landing page displaying an infinite scroll feed of research papers.
 * Responsibilities:
 * - Load and display papers in a paginated feed
 * - Handle paper expansion to show summaries
 * - Manage infinite scroll with intersection observer
 * - Preserve scroll position when expanding/collapsing papers
 * - Track user interactions (expand, read) for feed recommendations
 */

"use client";

import React, { useEffect, useState, useRef, useCallback, useLayoutEffect } from 'react';
import type { MinimalPaperItem } from '../types/paper';
import type { FeedResponse } from '../types/recommendation';
import { fetchPaperSummary, PaperSummaryResponse } from '../services/api';
import PaperCard from '../components/PaperCard';
import { usePaperImpression, trackPaperOpened } from '../hooks/useUmamiTracking';
import { useInteractionTracker } from '../hooks/useInteractionTracker';
import { useReadingTracker } from '../hooks/useReadingTracker';
import NewPapersBanner from '../components/NewPapersBanner';

// ============================================================================
// CONSTANTS
// ============================================================================

const ITEMS_PER_PAGE = 20;

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Estimates word count from a text string by splitting on whitespace.
 * @param text - The text to count words in
 * @returns The approximate word count
 */
function estimateWordCount(text: string | null | undefined): number {
  if (!text) return 0;
  return text.split(/\s+/).filter(Boolean).length;
}

// ============================================================================
// HELPER COMPONENTS
// ============================================================================

/**
 * A wrapper for PaperCard that adds impression tracking and reading tracking.
 * Uses useReadingTracker when the paper is expanded to measure active reading time.
 */
const PaperCardWithTracking = ({
  paper,
  isExpanded,
  isLoadingSummary,
  isGeneratingSummary,
  generateSummaryError,
  summary,
  onToggleExpand,
  onLoadSummary,
  onReadComplete,
}: {
  paper: MinimalPaperItem;
  isExpanded: boolean;
  isLoadingSummary: boolean;
  isGeneratingSummary?: boolean;
  generateSummaryError?: boolean;
  summary?: PaperSummaryResponse;
  onToggleExpand: (paperUuid: string) => void;
  onLoadSummary?: (paperUuid: string) => void;
  onReadComplete: (paperUuid: string, readingRatio: number) => void;
}) => {
  const impressionRef = usePaperImpression(paper.paperUuid, true);
  const wordCount = estimateWordCount(summary?.fiveMinuteSummary);
  const { ref: readingRef } = useReadingTracker(
    paper.paperUuid,
    wordCount,
    onReadComplete
  );

  return (
    <PaperCard
      ref={impressionRef}
      paper={paper}
      isExpanded={isExpanded}
      isLoadingSummary={isLoadingSummary}
      isGeneratingSummary={isGeneratingSummary}
      generateSummaryError={generateSummaryError}
      summary={summary}
      onToggleExpand={onToggleExpand}
      onLoadSummary={onLoadSummary}
      readingTrackerRef={isExpanded ? readingRef : undefined}
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
  const [generatingSummaries, setGeneratingSummaries] = useState<Set<string>>(new Set());
  const [generateErrors, setGenerateErrors] = useState<Set<string>>(new Set());
  const [pendingScrollAdjustment, setPendingScrollAdjustment] = useState<{ elementId: string; offsetFromTop: number } | null>(null);

  const observerTarget = useRef<HTMLDivElement>(null);

  // Interaction tracking for feed recommendations
  const { trackExpand, trackRead, getSessionPaperUuids } = useInteractionTracker();

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Loads a specific page of papers from the ranked feed API.
   * Sends already-loaded paper UUIDs as exclude list for deduplication.
   * @param page - The page number to load
   */
  const loadPage = useCallback(async (page: number): Promise<void> => {
    if (isLoading) return;

    try {
      setIsLoading(true);
      setError(null);

      // Build exclude list from already-loaded papers + session interactions
      const loadedUuids = papers.map((p) => p.paperUuid);
      const sessionUuids = getSessionPaperUuids();
      const excludePaperUuids = [...new Set([...loadedUuids, ...sessionUuids])];

      const response = await fetch('/api/papers/feed', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page, limit: ITEMS_PER_PAGE, excludePaperUuids }),
      });

      if (!response.ok) {
        throw new Error(`Feed request failed: ${response.status}`);
      }

      const result = (await response.json()) as FeedResponse;

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
  }, [isLoading, papers, paperSummaries, loadingSummaries, getSessionPaperUuids]); // eslint-disable-line react-hooks/exhaustive-deps

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
      // Track the "paper opened" event (Umami analytics)
      trackPaperOpened(paperUuid);
      // Track expand for feed recommendations
      trackExpand(paperUuid);

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

      // Auto-generate summary if it's null and not already generating
      const existing = paperSummaries.get(paperUuid);
      if (existing && !existing.fiveMinuteSummary && !generatingSummaries.has(paperUuid)) {
        generateSummaryForCard(paperUuid);
      }
    }
  }, [expandedPaperIds, paperSummaries, loadingSummaries, generatingSummaries, trackExpand]); // eslint-disable-line react-hooks/exhaustive-deps

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

  /**
   * Generates a summary on-demand for a paper card that has no summary yet.
   * @param paperUuid - The UUID of the paper to generate a summary for
   */
  const generateSummaryForCard = async (paperUuid: string): Promise<void> => {
    if (generatingSummaries.has(paperUuid)) return;

    setGeneratingSummaries(prev => new Set(prev).add(paperUuid));

    try {
      const response = await fetch(`/api/papers/${paperUuid}/generate-summary`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('Failed to generate summary');
      const data = await response.json();

      setPaperSummaries(prev => {
        const next = new Map(prev);
        const existing = next.get(paperUuid);
        if (existing) {
          next.set(paperUuid, { ...existing, fiveMinuteSummary: data.summary });
        }
        return next;
      });

      // Clear any previous error for this paper
      setGenerateErrors(prev => {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      });
    } catch (e) {
      console.error('Failed to generate summary:', e);
      setGenerateErrors(prev => new Set(prev).add(paperUuid));
    } finally {
      setGeneratingSummaries(prev => {
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
            const isGenerating = generatingSummaries.has(paper.paperUuid);
            const hasGenerateError = generateErrors.has(paper.paperUuid);

            return (
              <PaperCardWithTracking
                key={paper.paperUuid}
                paper={paper}
                isExpanded={isExpanded}
                isLoadingSummary={isLoadingSummary}
                isGeneratingSummary={isGenerating}
                generateSummaryError={hasGenerateError}
                summary={summary}
                onToggleExpand={toggleExpanded}
                onLoadSummary={loadPaperSummary}
                onReadComplete={trackRead}
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
