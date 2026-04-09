/**
 * Research Frontiers Service
 *
 * Queries the autoresearchhackathon tables and computes bump chart data
 * for the /frontiers page.
 *
 * Responsibilities:
 * - Fetch all themes and their paper assignments from Supabase
 * - Compute weekly paper counts per theme
 * - Compute velocity (% change vs rolling average) and status per theme
 * - Rank themes per week by paper count
 * - Return structured data for the bump chart + paper detail table
 */

import { createClient } from '@/lib/supabase/server';

// ============================================================================
// CONSTANTS
// ============================================================================

const ACCELERATING_THRESHOLD = 50;
const DECELERATING_THRESHOLD = -30;
const EMERGING_WINDOW_WEEKS = 2;

// ============================================================================
// TYPES
// ============================================================================

/** A single paper within a theme/week cell. */
export interface FrontierPaper {
  arxivId: string;
  title: string;
  publishedAt: string | null;
}

/** Per-week data point for a single theme on the bump chart. */
export interface ThemeWeekPoint {
  week: string;
  rank: number;
  paperCount: number;
  papers: FrontierPaper[];
}

/** A single theme line on the bump chart. */
export interface FrontierTheme {
  themeId: number;
  name: string;
  description: string;
  status: string;
  velocityPct: number | 'new';
  totalPapers: number;
  weeklyPoints: ThemeWeekPoint[];
}

/** Full response from the frontiers API. */
export interface FrontiersData {
  themes: FrontierTheme[];
  weeks: string[];
}

/** Raw row from the paper_themes join query. */
interface PaperThemeRow {
  theme_id: number;
  week: string;
  papers: {
    id: number;
    arxiv_id: string | null;
    title: string | null;
    published_at: string | null;
  };
  autoresearchhackathon_research_themes: {
    id: number;
    name: string;
    description: string;
  };
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

/**
 * Fetches all frontier data from the DB, computes velocity/status/ranks.
 * @returns Structured bump chart data with theme lines and week columns
 */
export async function getFrontiersData(): Promise<FrontiersData> {
  const supabase = await createClient();

  // Fetch all themes
  const { data: themesRaw, error: themesError } = await (supabase as any)
    .from('autoresearchhackathon_research_themes')
    .select('id, name, description, created_at');

  if (themesError) {
    throw new Error(`Failed to fetch research themes: ${themesError.message}`);
  }

  // Fetch all paper-theme assignments with paper details
  const { data: assignmentsRaw, error: assignmentsError } = await (supabase as any)
    .from('autoresearchhackathon_paper_themes')
    .select('theme_id, week, papers(id, arxiv_id, title, published_at), autoresearchhackathon_research_themes(id, name, description)');

  if (assignmentsError) {
    throw new Error(`Failed to fetch paper-theme assignments: ${assignmentsError.message}`);
  }

  const themes = (themesRaw ?? []) as Array<{ id: number; name: string; description: string; created_at: string }>;
  const assignments = (assignmentsRaw ?? []) as PaperThemeRow[];

  return buildFrontiersData(themes, assignments);
}

// ============================================================================
// MAIN LOGIC
// ============================================================================

/**
 * Builds the full FrontiersData response from raw DB rows.
 * @param themes - All research themes from the DB
 * @param assignments - All paper-theme assignment rows with joined paper data
 * @returns Structured data for the bump chart
 */
function buildFrontiersData(
  themes: Array<{ id: number; name: string; description: string; created_at: string }>,
  assignments: PaperThemeRow[],
): FrontiersData {
  // Collect all unique weeks, sorted ascending
  const weekSet = new Set<string>();
  for (const a of assignments) {
    weekSet.add(a.week);
  }
  const weeks = Array.from(weekSet).sort();

  if (weeks.length === 0) {
    return { themes: [], weeks: [] };
  }

  // Group assignments by theme_id -> week -> papers
  const themeWeekPapers = new Map<number, Map<string, FrontierPaper[]>>();
  for (const a of assignments) {
    if (!themeWeekPapers.has(a.theme_id)) {
      themeWeekPapers.set(a.theme_id, new Map());
    }
    const weekMap = themeWeekPapers.get(a.theme_id)!;
    if (!weekMap.has(a.week)) {
      weekMap.set(a.week, []);
    }
    weekMap.get(a.week)!.push({
      arxivId: a.papers?.arxiv_id ?? '',
      title: a.papers?.title ?? 'Untitled',
      publishedAt: a.papers?.published_at ?? null,
    });
  }

  // Build per-theme weekly counts for velocity/status computation
  const themeMap = new Map<number, { id: number; name: string; description: string; created_at: string }>();
  for (const t of themes) {
    themeMap.set(t.id, t);
  }

  // Compute weekly counts per theme, then rank per week
  const weeklyCountsByTheme = new Map<number, number[]>();
  for (const t of themes) {
    const weekMap = themeWeekPapers.get(t.id);
    const counts = weeks.map(w => weekMap?.get(w)?.length ?? 0);
    weeklyCountsByTheme.set(t.id, counts);
  }

  // Rank themes per week (1 = most papers)
  const weeklyRanks = computeWeeklyRanks(themes.map(t => t.id), weeklyCountsByTheme, weeks);

  // Build FrontierTheme objects
  const frontierThemes: FrontierTheme[] = [];
  for (const t of themes) {
    const counts = weeklyCountsByTheme.get(t.id) ?? [];
    const totalPapers = counts.reduce((a, b) => a + b, 0);
    if (totalPapers === 0) continue;

    const velocity = computeVelocity(counts);
    const firstSeenWeek = findFirstSeenWeek(counts, weeks);
    const status = determineStatus(velocity, counts, weeks, firstSeenWeek);

    const weekMap = themeWeekPapers.get(t.id);
    const ranks = weeklyRanks.get(t.id) ?? [];

    const weeklyPoints: ThemeWeekPoint[] = [];
    for (let i = 0; i < weeks.length; i++) {
      const count = counts[i];
      if (count === 0) continue;

      weeklyPoints.push({
        week: weeks[i],
        rank: ranks[i],
        paperCount: count,
        papers: weekMap?.get(weeks[i]) ?? [],
      });
    }

    frontierThemes.push({
      themeId: t.id,
      name: t.name,
      description: t.description,
      status,
      velocityPct: velocity,
      totalPapers,
      weeklyPoints,
    });
  }

  // Sort: emerging first, then accelerating, stable, decelerating, dormant
  frontierThemes.sort(sortByStatusAndVelocity);

  return { themes: frontierThemes, weeks };
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Computes rank per theme per week based on paper count (1 = most papers).
 * @param themeIds - All theme IDs
 * @param weeklyCountsByTheme - Map of themeId -> weekly count array
 * @param weeks - Sorted week strings
 * @returns Map of themeId -> rank array (one rank per week)
 */
function computeWeeklyRanks(
  themeIds: number[],
  weeklyCountsByTheme: Map<number, number[]>,
  weeks: string[],
): Map<number, number[]> {
  const result = new Map<number, number[]>();
  for (const id of themeIds) {
    result.set(id, new Array(weeks.length).fill(0));
  }

  for (let wi = 0; wi < weeks.length; wi++) {
    // Get all themes with papers this week, sorted by count descending
    const entries: { id: number; count: number }[] = [];
    for (const id of themeIds) {
      const counts = weeklyCountsByTheme.get(id) ?? [];
      const count = counts[wi] ?? 0;
      if (count > 0) {
        entries.push({ id, count });
      }
    }
    entries.sort((a, b) => b.count - a.count);

    for (let rank = 0; rank < entries.length; rank++) {
      result.get(entries[rank].id)![wi] = rank + 1;
    }
  }

  return result;
}

/**
 * Computes velocity as % change: most recent week vs average of previous weeks.
 * @param counts - Weekly paper counts in ascending order
 * @returns Percentage change, or "new" if no prior data but current week has papers
 */
function computeVelocity(counts: number[]): number | 'new' {
  if (counts.length < 2) return 0;

  const current = counts[counts.length - 1];
  const previous = counts.slice(0, -1);
  const avgPrevious = previous.reduce((a, b) => a + b, 0) / previous.length;

  if (avgPrevious === 0) {
    return current > 0 ? 'new' : 0;
  }

  return Math.round(((current - avgPrevious) / avgPrevious) * 100 * 10) / 10;
}

/**
 * Finds the first week string where the theme had papers.
 * @param counts - Weekly paper counts
 * @param weeks - Sorted week strings
 * @returns Week string or null
 */
function findFirstSeenWeek(counts: number[], weeks: string[]): string | null {
  for (let i = 0; i < counts.length; i++) {
    if (counts[i] > 0) return weeks[i];
  }
  return null;
}

/**
 * Determines theme status from velocity and recency.
 * @param velocity - Computed velocity (number or "new")
 * @param counts - Weekly paper counts
 * @param weeks - Sorted week strings
 * @param firstSeen - First week string with papers
 * @returns Status string
 */
function determineStatus(
  velocity: number | 'new',
  counts: number[],
  weeks: string[],
  firstSeen: string | null,
): string {
  const current = counts.length > 0 ? counts[counts.length - 1] : 0;

  if (current === 0) return 'dormant';

  if (firstSeen !== null) {
    const emergingCutoff = weeks.slice(-EMERGING_WINDOW_WEEKS);
    if (emergingCutoff.includes(firstSeen)) return 'emerging';
  }

  if (velocity === 'new') return 'emerging';
  if (velocity > ACCELERATING_THRESHOLD) return 'accelerating';
  if (velocity < DECELERATING_THRESHOLD) return 'decelerating';

  return 'stable';
}

const STATUS_ORDER: Record<string, number> = {
  emerging: 0,
  accelerating: 1,
  stable: 2,
  decelerating: 3,
  dormant: 4,
};

/**
 * Sort comparator: status priority first, then velocity descending.
 * @param a - First theme
 * @param b - Second theme
 * @returns Sort order number
 */
function sortByStatusAndVelocity(a: FrontierTheme, b: FrontierTheme): number {
  const aOrder = STATUS_ORDER[a.status] ?? 99;
  const bOrder = STATUS_ORDER[b.status] ?? 99;
  if (aOrder !== bOrder) return aOrder - bOrder;

  const aVel = a.velocityPct === 'new' ? 999999 : a.velocityPct;
  const bVel = b.velocityPct === 'new' ? 999999 : b.velocityPct;
  return bVel - aVel;
}
