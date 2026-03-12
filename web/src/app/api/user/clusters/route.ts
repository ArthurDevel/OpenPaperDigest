/**
 * User Clusters API Route
 *
 * Returns the authenticated user's preference clusters with top matching
 * paper titles per cluster, for display on the settings page.
 *
 * Responsibilities:
 * - Authenticate the user from Supabase session
 * - Fetch preference clusters via interactions service
 * - For each cluster, find the top 3 matching papers by embedding similarity
 * - Return clusters with metadata for UI display
 */

import { NextResponse } from 'next/server';
import { createClient } from '@/lib/supabase/server';
import { getPreferenceClusters } from '@/services/interactions.service';

// ============================================================================
// TYPES
// ============================================================================

interface ClusterWithPapers {
  clusterIndex: number;
  weight: number;
  interactionCount: number;
  updatedAt: string;
  topPapers: { paperUuid: string; title: string; similarity: number }[];
}

interface ClustersResponse {
  clusters: ClusterWithPapers[];
}

interface ErrorResponse {
  error: string;
}

// ============================================================================
// MAIN HANDLERS
// ============================================================================

/**
 * GET handler for user preference clusters.
 * Returns clusters with top 3 matching papers each.
 * @returns ClustersResponse on success, 401 if unauthenticated, 500 on error
 */
export async function GET(): Promise<NextResponse<ClustersResponse | ErrorResponse>> {
  try {
    const supabase = await createClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const clusters = await getPreferenceClusters(user.id);

    // For each cluster, find top 3 matching papers via the RPC
    const clustersWithPapers: ClusterWithPapers[] = await Promise.all(
      clusters.map(async (cluster) => {
        const vectorString = `[${cluster.embedding.join(',')}]`;

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const { data, error } = await (supabase.rpc as any)(
          'match_papers_by_embedding',
          {
            query_embedding: vectorString,
            match_count: 3,
            exclude_uuids: [],
          }
        );

        const topPapers = error
          ? []
          : ((data ?? []) as { paper_uuid: string; title: string; similarity: number }[]).map(
              (row) => ({
                paperUuid: row.paper_uuid,
                title: row.title ?? 'Untitled',
                similarity: Math.round(row.similarity * 1000) / 1000,
              })
            );

        return {
          clusterIndex: cluster.clusterIndex,
          weight: Math.round(cluster.weight * 100) / 100,
          interactionCount: cluster.interactionCount,
          updatedAt: cluster.updatedAt,
          topPapers,
        };
      })
    );

    return NextResponse.json({ clusters: clustersWithPapers });
  } catch (error) {
    console.error('Error fetching user clusters:', error);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
