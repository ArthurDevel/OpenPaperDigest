'use client';

/**
 * User Interests Page
 *
 * Displays the user's interacted papers (opened, saved, read) grouped into
 * clusters by topic similarity. Uses on-the-fly k-means clustering with a
 * slider to control the number of clusters.
 *
 * Responsibilities:
 * - Fetch clustered papers from the API with configurable maxClusters
 * - Display a slider for adjusting the number of clusters
 * - Show papers grouped by cluster in a card grid
 */

import React, { useEffect, useRef, useState } from 'react';
import { useSession } from '@/services/auth';
import { Loader, Search } from 'lucide-react';
import type { InterestCluster } from '@/types/interests';

// ============================================================================
// CONSTANTS
// ============================================================================

const DEFAULT_MAX_CLUSTERS = 5;
const MIN_CLUSTERS = 1;
const MAX_CLUSTERS = 10;
const DEBOUNCE_MS = 300;

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * Interests page showing interacted papers grouped by topic clusters.
 * @returns Page component with cluster slider and paper groups
 */
export default function UserInterestsPage(): React.JSX.Element {
  const { user } = useSession();
  const [clusters, setClusters] = useState<InterestCluster[]>([]);
  const [totalPapers, setTotalPapers] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>('');
  const [maxClusters, setMaxClusters] = useState<number>(DEFAULT_MAX_CLUSTERS);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch clusters with debounce when maxClusters or user changes
  useEffect(() => {
    if (!user?.id) {
      setLoading(false);
      return;
    }

    // Debounce the fetch to avoid spamming while dragging the slider
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(async () => {
      try {
        setLoading(true);
        const res = await fetch(`/api/users/me/interests?maxClusters=${maxClusters}`);
        if (!res.ok) {
          throw new Error(`Failed to fetch interests: ${res.status}`);
        }
        const data = await res.json();
        setClusters(data.clusters ?? []);
        setTotalPapers(data.totalPapers ?? 0);
      } catch (e: unknown) {
        const message = e instanceof Error ? e.message : 'Failed to load interests';
        setError(message);
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [user?.id, maxClusters]);

  // ============================================================================
  // EVENT HANDLERS
  // ============================================================================

  /**
   * Updates the max clusters value from the slider input.
   * @param e - Change event from the range input
   */
  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    setMaxClusters(parseInt(e.target.value, 10));
  };

  /**
   * Stores a cluster's centroid in sessionStorage and opens the discover page in a new tab.
   * @param centroid - The cluster centroid embedding vector
   */
  const handleFindSimilar = (centroid: number[]): void => {
    sessionStorage.setItem('interestSearchCentroid', JSON.stringify(centroid));
    window.open('/discover', '_blank');
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="p-6 h-full flex flex-col min-h-0 overflow-auto">
      <h1 className="text-xl font-semibold">My interests</h1>

      {/* Debug disclaimer */}
      <div className="mb-4 px-3 py-2 rounded-md border border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-900/30 text-xs text-amber-800 dark:text-amber-300">
        Internal debug view -- we are building a recommendation algorithm and use this page to
        inspect how papers cluster based on your reading activity.
      </div>

      <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 mb-4">
        Papers you have opened, saved, or read, grouped by topic similarity.
      </p>

      {/* Cluster slider */}
      <div className="flex items-center gap-3 mb-4">
        <label htmlFor="cluster-slider" className="text-sm text-gray-600 dark:text-gray-300">
          Max clusters:
        </label>
        <input
          id="cluster-slider"
          type="range"
          min={MIN_CLUSTERS}
          max={MAX_CLUSTERS}
          value={maxClusters}
          onChange={handleSliderChange}
          className="w-48 accent-blue-600"
        />
        <span className="text-sm font-medium w-6 text-center">{maxClusters}</span>
        {totalPapers > 0 && (
          <span className="text-xs text-gray-400 dark:text-gray-500 ml-2">
            ({totalPapers} papers)
          </span>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
          <Loader className="animate-spin w-4 h-4 mr-2" /> Clustering papers...
        </div>
      ) : clusters.length === 0 ? (
        <div className="p-4 rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 text-sm text-gray-600 dark:text-gray-300">
          No interacted papers yet. Start opening, reading, or saving papers to see your interests here.
        </div>
      ) : (
        <div className="space-y-6">
          {clusters.map((cluster) => (
            <ClusterSection
              key={cluster.clusterIndex}
              cluster={cluster}
              onFindSimilar={handleFindSimilar}
            />
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
 * Renders a single cluster as a section with a heading, search button, and a grid of paper cards.
 * @param cluster - The cluster data to display
 * @param onFindSimilar - Callback to trigger similar paper search for this cluster's centroid
 * @returns Section with cluster heading, search button, and paper grid
 */
function ClusterSection({
  cluster,
  onFindSimilar,
}: {
  cluster: InterestCluster;
  onFindSimilar: (centroid: number[]) => void;
}): React.JSX.Element {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <h2 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Group {cluster.clusterIndex + 1}
        </h2>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          ({cluster.papers.length} {cluster.papers.length === 1 ? 'paper' : 'papers'})
        </span>
        <button
          onClick={() => onFindSimilar(cluster.centroid)}
          className="ml-2 flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 transition-colors"
        >
          <Search className="w-3 h-3" />
          Find similar papers
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {cluster.papers.map((paper) => {
          const href = `/paper/${encodeURIComponent(paper.slug || paper.paperUuid)}`;
          return (
            <a
              key={paper.paperUuid}
              href={href}
              className="flex gap-3 p-3 rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
            >
              {paper.thumbnailUrl ? (
                <img
                  src={paper.thumbnailUrl}
                  alt=""
                  className="w-16 h-12 object-cover rounded flex-shrink-0"
                />
              ) : (
                <div className="w-16 h-12 bg-gray-200 dark:bg-gray-700 rounded flex-shrink-0" />
              )}
              <div className="min-w-0">
                <p className="text-sm font-medium line-clamp-2">{paper.title || 'Untitled'}</p>
                {paper.authors && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">
                    {paper.authors}
                  </p>
                )}
              </div>
            </a>
          );
        })}
      </div>
    </div>
  );
}
