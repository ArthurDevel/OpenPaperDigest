"use client";

/**
 * Discover Page
 *
 * Shows papers similar to a cluster centroid, displayed as a feed using
 * PaperCard. The centroid embedding is read from sessionStorage (stored
 * by the interests page when the user clicks "Find similar papers").
 *
 * Responsibilities:
 * - Read centroid from sessionStorage and search for similar papers
 * - Display results in a feed layout identical to the search page
 * - Support expanding papers to view summaries
 */

import React, { useState, useEffect, useCallback } from 'react';
import { ArrowLeft, Loader } from 'lucide-react';
import type { MinimalPaperItem } from '@/types/paper';
import { fetchPaperSummary, PaperSummaryResponse } from '@/services/api';
import PaperCard from '@/components/PaperCard';

// ============================================================================
// CONSTANTS
// ============================================================================

const SESSION_STORAGE_KEY = 'interestSearchCentroid';

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Discover page showing papers similar to a cluster centroid.
 * @returns Feed-style page with similar paper results
 */
export default function DiscoverPage() {
  const [papers, setPapers] = useState<MinimalPaperItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [expandedPaperIds, setExpandedPaperIds] = useState<Set<string>>(new Set());
  const [paperSummaries, setPaperSummaries] = useState<Map<string, PaperSummaryResponse>>(new Map());
  const [loadingSummaries, setLoadingSummaries] = useState<Set<string>>(new Set());

  // Fetch similar papers on mount
  useEffect(() => {
    const run = async () => {
      const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (!stored) {
        setError('No cluster centroid found. Go to My interests and click "Find similar papers" on a cluster.');
        setLoading(false);
        return;
      }

      let centroid: number[];
      try {
        centroid = JSON.parse(stored);
      } catch {
        setError('Invalid centroid data.');
        setLoading(false);
        return;
      }

      try {
        const res = await fetch('/api/users/me/interests/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ embedding: centroid }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `Search failed (${res.status})`);
        }

        const data = await res.json();
        const items = (data.items ?? []) as MinimalPaperItem[];
        setPapers(items);

        // Preload summaries for all results
        for (const paper of items) {
          loadPaperSummary(paper.paperUuid);
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to search');
      } finally {
        setLoading(false);
      }
    };

    run();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Loads and caches a paper summary.
   * @param paperUuid - UUID of the paper to load
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
   * Toggles expanded state for a paper (only one at a time).
   * @param paperUuid - UUID of the paper to toggle
   */
  const toggleExpanded = useCallback((paperUuid: string): void => {
    setExpandedPaperIds(prev => {
      if (prev.has(paperUuid)) {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      }
      return new Set([paperUuid]);
    });

    if (!paperSummaries.has(paperUuid) && !loadingSummaries.has(paperUuid)) {
      loadPaperSummary(paperUuid);
    }
  }, [paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <a
          href="/user/interests"
          className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors mb-4"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to My interests
        </a>

        <h1 className="text-3xl font-bold mb-2">Discover</h1>

        {/* Debug disclaimer */}
        <div className="mb-6 px-3 py-2 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/30 text-xs text-amber-800 dark:text-amber-300">
          Internal debug view -- these are papers from our database most similar to the
          selected cluster centroid, excluding papers you have already interacted with.
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center text-sm text-gray-600 dark:text-gray-300">
            <Loader className="animate-spin w-4 h-4 mr-2" /> Searching for similar papers...
          </div>
        ) : papers.length === 0 && !error ? (
          <div className="text-gray-600 dark:text-gray-300">No similar papers found.</div>
        ) : (
          <div className="space-y-4">
            {papers.map((paper) => (
              <PaperCard
                key={paper.paperUuid}
                paper={paper}
                isExpanded={expandedPaperIds.has(paper.paperUuid)}
                isLoadingSummary={loadingSummaries.has(paper.paperUuid)}
                summary={paperSummaries.get(paper.paperUuid)}
                onToggleExpand={toggleExpanded}
                onLoadSummary={loadPaperSummary}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
