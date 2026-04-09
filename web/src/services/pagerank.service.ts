/**
 * PageRank Service
 *
 * Fetches paper-author pagerank data and aggregates the best (max) author
 * pagerank percentile per paper. Used by the /pagerank scatter chart page.
 *
 * Responsibilities:
 * - Query paper_authors with nested select on papers + authors
 * - Filter out rows where authors have no pagerank data
 * - Group by paper and pick the max author percentile per paper
 */

import { createClient } from '@/lib/supabase/server';

// ============================================================================
// TYPES
// ============================================================================

/**
 * A single point in the pagerank scatter chart.
 */
export interface PageRankScatterItem {
  /** ISO timestamp of when the paper was published on arXiv (null if unknown) */
  publishedAt: string | null;
  /** ISO timestamp of when the paper was ingested (fallback) */
  createdAt: string;
  /** Paper title */
  title: string;
  /** arXiv identifier */
  arxivId: string;
  /** Highest pagerank percentile among the paper's authors (0-100) */
  bestAuthorPercentile: number;
}

/**
 * Raw row shape returned by the Supabase nested select on paper_authors.
 * The types file hasn't been regenerated for the pagerank column, so this
 * is defined manually.
 */
interface PaperAuthorRow {
  papers: {
    id: number;
    published_at: string | null;
    created_at: string;
    title: string;
    arxiv_id: string;
  };
  authors: {
    pagerank: { percentile: number } | null;
  };
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

/**
 * Fetches all papers with at least one author that has pagerank data,
 * and returns one item per paper with the best (highest) author percentile.
 * @returns Array of scatter chart items sorted by created_at ascending
 */
export async function getPageRankScatterData(): Promise<PageRankScatterItem[]> {
  const supabase = await createClient();

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data, error } = await (supabase as any)
    .from('paper_authors')
    .select('papers(id, published_at, created_at, title, arxiv_id), authors(pagerank)')
    .not('authors.pagerank', 'is', null);

  if (error) {
    throw new Error(`Failed to fetch pagerank data: ${error.message}`);
  }

  const rows = (data ?? []) as PaperAuthorRow[];

  return aggregateBestPercentilePerPaper(rows);
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Groups paper-author rows by paper ID and picks the max author percentile.
 * @param rows - Raw paper-author rows from Supabase
 * @returns Deduplicated array with one entry per paper, sorted by created_at
 */
function aggregateBestPercentilePerPaper(rows: PaperAuthorRow[]): PageRankScatterItem[] {
  const paperMap = new Map<number, { item: Omit<PageRankScatterItem, 'bestAuthorPercentile'>; maxPercentile: number }>();

  for (const row of rows) {
    const paper = row.papers;
    const percentile = row.authors?.pagerank?.percentile;

    if (percentile == null) continue;

    const existing = paperMap.get(paper.id);
    if (existing) {
      existing.maxPercentile = Math.max(existing.maxPercentile, percentile);
    } else {
      paperMap.set(paper.id, {
        item: {
          publishedAt: paper.published_at,
          createdAt: paper.created_at,
          title: paper.title,
          arxivId: paper.arxiv_id,
        },
        maxPercentile: percentile,
      });
    }
  }

  return Array.from(paperMap.values())
    .map(({ item, maxPercentile }) => ({
      ...item,
      bestAuthorPercentile: maxPercentile,
    }))
    .sort((a, b) => {
      const aDate = a.publishedAt ?? '\uffff';
      const bDate = b.publishedAt ?? '\uffff';
      return aDate.localeCompare(bDate);
    });
}
