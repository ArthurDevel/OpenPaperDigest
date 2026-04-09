"use client";

import { useEffect, useState } from 'react';
import { getPageRankScatterData, type PageRankScatterItem } from '../../services/api';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

/**
 * PageRank Scatter Chart Page
 *
 * Displays a 2D scatter chart showing each paper's best author PageRank
 * percentile (Y) over ingestion time (X). Each dot is a paper; hover shows
 * title and arXiv link. No auth required.
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const ARXIV_ABS_BASE = 'https://arxiv.org/abs/';

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * Custom tooltip for scatter chart dots.
 * Shows paper title, date, percentile, and a clickable arXiv link.
 */
function ScatterTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) return null;

  const item = payload[0].payload as PageRankScatterItem;
  const date = new Date(item.createdAt);
  const formatted = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md p-3 shadow-lg max-w-sm">
      <p className="font-semibold text-sm leading-tight">{item.title}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{formatted}</p>
      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">
        Best author percentile: <span className="font-medium">{item.bestAuthorPercentile.toFixed(1)}</span>
      </p>
      <a
        href={`${ARXIV_ABS_BASE}${item.arxivId}`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1 block"
      >
        {item.arxivId}
      </a>
    </div>
  );
}

// ============================================================================
// RENDER
// ============================================================================

export default function PageRankPage() {
  const [data, setData] = useState<PageRankScatterItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await getPageRankScatterData();
        setData(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  /**
   * Format ISO date string for X axis tick labels.
   */
  const formatDateTick = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">Loading pagerank data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-red-500">Error: {error}</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">No papers with author pagerank data found.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">Author PageRank by Ingestion Date</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Each dot is a paper. Y axis shows the best (highest) author PageRank percentile.
      </p>
      <div className="w-full h-[600px]">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 20, right: 30, bottom: 20, left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="createdAt"
              name="Date"
              tickFormatter={formatDateTick}
              type="category"
            />
            <YAxis
              dataKey="bestAuthorPercentile"
              name="Best Author Percentile"
              domain={[0, 100]}
              unit="%"
            />
            <Tooltip content={<ScatterTooltip />} />
            <Scatter
              name="Papers"
              data={data}
              fill="#6366f1"
              opacity={0.7}
              r={4}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
