'use client';

/**
 * User Personalization Page
 *
 * Shows the user's active preference clusters that drive feed personalization.
 * Each cluster shows its strength, interaction count, last update, and top
 * matching papers.
 *
 * Responsibilities:
 * - Fetch preference clusters from the API
 * - Display clusters as cards with metadata and top papers
 * - Show empty state when no clusters exist yet
 */

import React, { useEffect, useState } from 'react';
import { useSession } from '@/services/auth';
import { Loader } from 'lucide-react';

// ============================================================================
// TYPES
// ============================================================================

interface ClusterTopPaper {
  paperUuid: string;
  title: string;
  similarity: number;
}

interface ClusterData {
  clusterIndex: number;
  weight: number;
  interactionCount: number;
  updatedAt: string;
  topPapers: ClusterTopPaper[];
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Personalization page showing active preference clusters.
 * @returns Page component displaying user preference clusters
 */
export default function UserPersonalizationPage() {
  const { user } = useSession();
  const [clusters, setClusters] = useState<ClusterData[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');

  // Fetch clusters from API
  useEffect(() => {
    const fetchClusters = async () => {
      if (!user?.id) {
        setLoading(false);
        return;
      }
      try {
        setLoading(true);
        const res = await fetch('/api/user/clusters');
        if (!res.ok) {
          throw new Error(`Failed to fetch clusters: ${res.status}`);
        }
        const data = await res.json();
        setClusters(data.clusters ?? []);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load clusters';
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    fetchClusters();
  }, [user?.id]);

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="p-6 h-full flex flex-col min-h-0 overflow-auto">
      <h1 className="text-xl font-semibold">Personalization</h1>
      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 mb-4">
        As you interact with papers, we build interest clusters to personalize your feed.
        Each cluster represents a topic area you&apos;ve shown interest in.
      </p>

        {error && (
          <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
            <Loader className="animate-spin w-4 h-4 mr-2" /> Loading clusters...
          </div>
        ) : clusters.length === 0 ? (
          <div className="p-4 rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-600 dark:text-gray-300">
            No interest clusters yet. Start reading and expanding papers on the home feed to build your personalized profile.
          </div>
        ) : (
          <div className="space-y-3">
            {clusters.map((cluster) => (
              <ClusterCard key={cluster.clusterIndex} cluster={cluster} />
            ))}
          </div>
        )}
    </div>
  );
}

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * Renders a single preference cluster as a card.
 * @param cluster - The cluster data to display
 * @returns Card with cluster metadata and top matching papers
 */
function ClusterCard({ cluster }: { cluster: ClusterData }) {
  const updatedDate = new Date(cluster.updatedAt);
  const daysAgo = Math.floor((Date.now() - updatedDate.getTime()) / (1000 * 60 * 60 * 24));
  const updatedLabel = daysAgo === 0 ? 'today' : daysAgo === 1 ? '1 day ago' : `${daysAgo} days ago`;

  return (
    <div className="p-4 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
      {/* Header row */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">Cluster {cluster.clusterIndex + 1}</span>
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Updated {updatedLabel}
        </span>
      </div>

      {/* Stats row */}
      <div className="flex gap-4 mb-3 text-xs text-gray-600 dark:text-gray-400">
        <div>
          <span className="text-gray-400 dark:text-gray-500">Strength: </span>
          <span className="font-medium text-gray-700 dark:text-gray-300">{cluster.weight}</span>
        </div>
        <div>
          <span className="text-gray-400 dark:text-gray-500">Interactions: </span>
          <span className="font-medium text-gray-700 dark:text-gray-300">{cluster.interactionCount}</span>
        </div>
      </div>

      {/* Top matching papers */}
      {cluster.topPapers.length > 0 && (
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">Top matching papers:</p>
          <ul className="space-y-1">
            {cluster.topPapers.map((paper) => (
              <li key={paper.paperUuid} className="flex items-start gap-2 text-xs">
                <span className="shrink-0 mt-0.5 px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-mono">
                  {paper.similarity.toFixed(2)}
                </span>
                <span className="text-gray-700 dark:text-gray-300 line-clamp-1">{paper.title}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
