"use client";

import React, { useState, useCallback } from 'react';
import { Search } from 'lucide-react';
import type { MinimalPaperItem } from '../../types/paper';
import { fetchPaperSummary, PaperSummaryResponse } from '../../services/api';
import PaperCard from '../../components/PaperCard';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [papers, setPapers] = useState<MinimalPaperItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const [expandedPaperIds, setExpandedPaperIds] = useState<Set<string>>(new Set());
  const [paperSummaries, setPaperSummaries] = useState<Map<string, PaperSummaryResponse>>(new Map());
  const [loadingSummaries, setLoadingSummaries] = useState<Set<string>>(new Set());

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;

    setIsSearching(true);
    setError(null);
    setHasSearched(true);
    setExpandedPaperIds(new Set());

    try {
      const res = await fetch('/api/papers/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
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
        if (!paperSummaries.has(paper.paperUuid)) {
          loadPaperSummary(paper.paperUuid);
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setIsSearching(false);
    }
  }

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

  const toggleExpanded = useCallback((paperUuid: string): void => {
    setExpandedPaperIds(prev => {
      if (prev.has(paperUuid)) {
        const next = new Set(prev);
        next.delete(paperUuid);
        return next;
      }
      // Collapse previous, expand new
      return new Set([paperUuid]);
    });

    if (!paperSummaries.has(paperUuid) && !loadingSummaries.has(paperUuid)) {
      loadPaperSummary(paperUuid);
    }
  }, [paperSummaries, loadingSummaries]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="w-full">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
        <h1 className="text-3xl font-bold mb-2">Search Papers</h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-6">
          Describe topics you&apos;re interested in to find relevant papers.
        </p>

        <form onSubmit={handleSearch} className="flex gap-2 mb-8">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g., transformer architectures for computer vision"
            className="flex-1 px-3 py-2 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button
            type="submit"
            disabled={isSearching || !query.trim()}
            className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <Search size={16} />
            Search
          </button>
        </form>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
            {error}
          </div>
        )}

        {isSearching ? (
          <div className="text-gray-600 dark:text-gray-300">Searching…</div>
        ) : hasSearched && papers.length === 0 ? (
          <div className="text-gray-600 dark:text-gray-300">No papers found. Try a different description.</div>
        ) : papers.length > 0 ? (
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
        ) : null}
      </div>
    </main>
  );
}
