"use client";

/**
 * Research Frontiers Bump Chart Page
 *
 * Displays a bump chart showing research theme rankings over time.
 * Each theme is a line connecting weekly rank positions. Color encodes
 * velocity (green = accelerating, yellow = flat, red = declining).
 * Clicking a circle shows the papers for that theme/week in a table below.
 *
 * Responsibilities:
 * - Fetch frontiers data from /api/frontiers
 * - Render an SVG bump chart with bezier-curved lines
 * - Color lines by velocity (continuous green-yellow-red gradient)
 * - Show labels on the right for themes present in the latest week,
 *   on the left for themes that disappeared before the latest week
 * - On circle click, show a paper table below the chart
 */

import { useEffect, useState, useMemo } from 'react';
import { getFrontiersData, type FrontiersData, type FrontierTheme, type FrontierPaper } from '../../services/api';

// ============================================================================
// CONSTANTS
// ============================================================================

const CHART_PADDING_LEFT = 40;
const CHART_PADDING_RIGHT = 280;
const CHART_PADDING_TOP = 50;
const CHART_PADDING_BOTTOM = 50;
const CIRCLE_RADIUS = 8;
const ARXIV_ABS_BASE = 'https://arxiv.org/abs/';

const STATUS_COLORS: Record<string, string> = {
  emerging: '#10b981',
  accelerating: '#22c55e',
  stable: '#eab308',
  decelerating: '#f97316',
  dormant: '#ef4444',
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Computes a color on the green-yellow-red gradient based on rank change.
 * Negative rankDelta = rank improved (moved up) = green.
 * Zero = stable = yellow.
 * Positive rankDelta = rank worsened (moved down) = red.
 * @param rankDelta - Change in rank (current - previous). Negative = improvement.
 * @returns Color string
 */
function getSegmentColor(rankDelta: number): string {
  // Clamp to [-10, 10] for color mapping, then normalize to [-1, 1]
  const clamped = Math.max(-10, Math.min(10, rankDelta));
  const normalized = clamped / 10;

  if (normalized <= 0) {
    // -1 = strong improvement = bright green, 0 = stable = yellow
    const t = -normalized;
    return interpolateColor('#eab308', '#10b981', t);
  } else {
    // 0 = stable = yellow, 1 = strong decline = red
    return interpolateColor('#eab308', '#ef4444', normalized);
  }
}

/**
 * Computes a color for a circle based on overall theme velocity.
 * @param velocityPct - Velocity percentage or "new"
 * @returns Color string
 */
function getVelocityColor(velocityPct: number | 'new'): string {
  if (velocityPct === 'new') return '#10b981';
  const v = Math.max(-100, Math.min(100, velocityPct));
  if (v >= 0) {
    return interpolateColor('#eab308', '#10b981', v / 100);
  } else {
    return interpolateColor('#ef4444', '#eab308', (v + 100) / 100);
  }
}

/**
 * Linearly interpolates between two hex colors.
 * @param colorA - Start hex color
 * @param colorB - End hex color
 * @param t - Interpolation factor (0-1)
 * @returns Interpolated hex color
 */
function interpolateColor(colorA: string, colorB: string, t: number): string {
  const a = hexToRgb(colorA);
  const b = hexToRgb(colorB);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

/**
 * Converts hex color to RGB object.
 * @param hex - Hex color string (e.g. "#10b981")
 * @returns Object with r, g, b values
 */
function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const h = hex.replace('#', '');
  return {
    r: parseInt(h.substring(0, 2), 16),
    g: parseInt(h.substring(2, 4), 16),
    b: parseInt(h.substring(4, 6), 16),
  };
}

/**
 * Blends two RGB color strings together.
 * @param colorA - First color (rgb or hex)
 * @param colorB - Second color (rgb or hex)
 * @param t - Blend factor: 0 = all colorA, 1 = all colorB
 * @returns Blended color as rgb() string
 */
function blendColors(colorA: string, colorB: string, t: number): string {
  const a = parseColor(colorA);
  const b = parseColor(colorB);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

/**
 * Parses either hex (#rrggbb) or rgb(r, g, b) strings into {r, g, b}.
 * @param color - Color string in hex or rgb format
 * @returns Object with r, g, b values
 */
function parseColor(color: string): { r: number; g: number; b: number } {
  if (color.startsWith('#')) return hexToRgb(color);
  const match = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
  if (match) return { r: +match[1], g: +match[2], b: +match[3] };
  return { r: 128, g: 128, b: 128 };
}

/**
 * Formats a week date string to a human-readable label.
 * @param week - ISO date string like "2026-01-05"
 * @returns Formatted string like "Jan 5"
 */
function formatWeekLabel(week: string): string {
  const date = new Date(week + 'T00:00:00');
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Computes how long ago a date was, as a human-readable string.
 * @param dateStr - ISO date string
 * @returns String like "2d ago", "3w ago", "1m ago"
 */
function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '';
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays < 1) return 'today';
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)}m ago`;
  return `${Math.floor(diffDays / 365)}y ago`;
}

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * Legend showing the color gradient meaning.
 */
function ChartLegend() {
  return (
    <div className="flex items-center gap-6 mb-4 text-sm text-gray-300">
      <div className="flex items-center gap-2">
        <span>Declining</span>
        <div
          className="w-24 h-3 rounded"
          style={{
            background: 'linear-gradient(to right, #ef4444, #eab308, #10b981)',
          }}
        />
        <span>Accelerating</span>
      </div>
      <div className="flex items-center gap-2">
        <svg width="24" height="12">
          <line x1="0" y1="6" x2="24" y2="6" stroke="#ef4444" strokeWidth="2" strokeDasharray="4 3" />
        </svg>
        <span>Dormant</span>
      </div>
    </div>
  );
}

/**
 * Table showing papers for a selected theme/week combination.
 */
function PaperTable({
  papers,
  themeName,
  week,
}: {
  papers: FrontierPaper[];
  themeName: string;
  week: string;
}) {
  return (
    <div className="mt-6 bg-gray-800 rounded-lg p-4 border border-gray-700">
      <h3 className="text-lg font-semibold text-gray-100 mb-3">
        {themeName} -- {formatWeekLabel(week)}
      </h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 border-b border-gray-700">
            <th className="text-left py-2 pr-4">Paper</th>
            <th className="text-left py-2 pr-4">arXiv ID</th>
            <th className="text-right py-2">Published</th>
          </tr>
        </thead>
        <tbody>
          {papers.map((paper, i) => (
            <tr key={i} className="border-b border-gray-700/50 hover:bg-gray-700/30">
              <td className="py-2 pr-4 text-gray-200">{paper.title}</td>
              <td className="py-2 pr-4">
                <a
                  href={`${ARXIV_ABS_BASE}${paper.arxivId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  {paper.arxivId}
                </a>
              </td>
              <td className="py-2 text-right">
                <span className="inline-block bg-gray-700 text-gray-300 px-2 py-0.5 rounded text-xs">
                  {timeAgo(paper.publishedAt)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================================
// BUMP CHART COMPONENT
// ============================================================================

/**
 * SVG-based bump chart.
 * Each theme is a line, X = week, Y = rank, with bezier curves between points.
 */
function BumpChart({
  themes,
  weeks,
  onCircleClick,
  selectedThemeId,
  selectedWeek,
}: {
  themes: FrontierTheme[];
  weeks: string[];
  onCircleClick: (themeId: number, week: string) => void;
  selectedThemeId: number | null;
  selectedWeek: string | null;
}) {
  // Compute max rank across all weeks for Y-axis scaling
  const maxRank = useMemo(() => {
    let max = 1;
    for (const theme of themes) {
      for (const point of theme.weeklyPoints) {
        if (point.rank > max) max = point.rank;
      }
    }
    return max;
  }, [themes]);

  const chartWidth = 900;
  const plotWidth = chartWidth - CHART_PADDING_LEFT - CHART_PADDING_RIGHT;
  const chartHeight = Math.max(400, maxRank * 30 + CHART_PADDING_TOP + CHART_PADDING_BOTTOM);
  const plotHeight = chartHeight - CHART_PADDING_TOP - CHART_PADDING_BOTTOM;

  /** Maps a week index to an X coordinate. */
  const weekToX = (weekIdx: number): number => {
    if (weeks.length <= 1) return CHART_PADDING_LEFT + plotWidth / 2;
    return CHART_PADDING_LEFT + (weekIdx / (weeks.length - 1)) * plotWidth;
  };

  /** Maps a rank to a Y coordinate (rank 1 = top). */
  const rankToY = (rank: number): number => {
    if (maxRank <= 1) return CHART_PADDING_TOP + plotHeight / 2;
    return CHART_PADDING_TOP + ((rank - 1) / (maxRank - 1)) * plotHeight;
  };

  /** Builds per-segment bezier paths with colors based on rank change. */
  const buildSegments = (theme: FrontierTheme): Array<{
    path: string;
    startColor: string;
    endColor: string;
    gradientId: string;
  }> => {
    const points = theme.weeklyPoints.map((wp) => ({
      x: weekToX(weeks.indexOf(wp.week)),
      y: rankToY(wp.rank),
      rank: wp.rank,
    }));

    if (points.length < 2) return [];

    const segments = [];
    for (let i = 1; i < points.length; i++) {
      const prev = points[i - 1];
      const curr = points[i];
      const cpOffset = (curr.x - prev.x) * 0.4;

      const rankDelta = curr.rank - prev.rank;
      const segColor = getSegmentColor(rankDelta);

      // For gradient overflow: blend the end of prev segment into start of this one
      // Use the previous segment's color as start, this segment's color as end
      let startColor = segColor;
      if (i >= 2) {
        const prevPrevRank = points[i - 2].rank;
        const prevDelta = prev.rank - prevPrevRank;
        const prevColor = getSegmentColor(prevDelta);
        // Blend: 30% previous segment color, 70% current for a smooth transition
        startColor = blendColors(prevColor, segColor, 0.3);
      }

      const gradientId = `grad-${theme.themeId}-seg${i}`;
      const path = `M ${prev.x} ${prev.y} C ${prev.x + cpOffset} ${prev.y}, ${curr.x - cpOffset} ${curr.y}, ${curr.x} ${curr.y}`;

      segments.push({ path, startColor, endColor: segColor, gradientId });
    }

    return segments;
  };

  /** Determines if a theme has data in the latest week. */
  const isActiveInLastWeek = (theme: FrontierTheme): boolean => {
    const lastWeek = weeks[weeks.length - 1];
    return theme.weeklyPoints.some((wp) => wp.week === lastWeek);
  };

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className="w-full"
      style={{ maxHeight: '70vh' }}
    >
      {/* Background */}
      <rect width={chartWidth} height={chartHeight} fill="#1a1f2e" rx="8" />

      {/* Week axis labels */}
      {weeks.map((week, i) => (
        <text
          key={week}
          x={weekToX(i)}
          y={chartHeight - 15}
          textAnchor="middle"
          fill="#9ca3af"
          fontSize="12"
        >
          {formatWeekLabel(week)}
        </text>
      ))}

      {/* Vertical grid lines */}
      {weeks.map((week, i) => (
        <line
          key={`grid-${week}`}
          x1={weekToX(i)}
          y1={CHART_PADDING_TOP - 10}
          x2={weekToX(i)}
          y2={chartHeight - CHART_PADDING_BOTTOM + 10}
          stroke="#2d3548"
          strokeWidth="1"
        />
      ))}

      {/* Gradient definitions for all theme segments */}
      <defs>
        {themes.map((theme) => {
          const segments = buildSegments(theme);
          return segments.map((seg) => (
            <linearGradient key={seg.gradientId} id={seg.gradientId} x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor={seg.startColor} />
              <stop offset="100%" stopColor={seg.endColor} />
            </linearGradient>
          ));
        })}
      </defs>

      {/* Theme lines */}
      {themes.map((theme) => {
        const isDormant = theme.status === 'dormant';
        const isSelected = theme.themeId === selectedThemeId;
        const segments = buildSegments(theme);

        if (segments.length === 0 && theme.weeklyPoints.length === 0) return null;

        // Label color: use the last segment's end color, or velocity color for single-point themes
        const labelColor = segments.length > 0
          ? segments[segments.length - 1].endColor
          : getVelocityColor(theme.velocityPct);

        return (
          <g key={theme.themeId}>
            {/* Per-segment gradient lines */}
            {segments.map((seg) => (
              <path
                key={seg.gradientId}
                d={seg.path}
                fill="none"
                stroke={`url(#${seg.gradientId})`}
                strokeWidth={isSelected ? 3 : 2}
                strokeDasharray={isDormant ? '6 4' : undefined}
                opacity={selectedThemeId !== null && !isSelected ? 0.25 : 0.8}
              />
            ))}

            {/* Circles at each week-point */}
            {theme.weeklyPoints.map((wp, wpIdx) => {
              const x = weekToX(weeks.indexOf(wp.week));
              const y = rankToY(wp.rank);
              const isThisSelected = selectedThemeId === theme.themeId && selectedWeek === wp.week;

              // Circle color: based on rank change from previous point
              let circleColor: string;
              if (wpIdx === 0 && segments.length > 0) {
                circleColor = segments[0].startColor;
              } else if (wpIdx > 0 && wpIdx - 1 < segments.length) {
                circleColor = segments[wpIdx - 1].endColor;
              } else {
                circleColor = getVelocityColor(theme.velocityPct);
              }

              return (
                <g key={`${theme.themeId}-${wp.week}`}>
                  <circle
                    cx={x}
                    cy={y}
                    r={isThisSelected ? CIRCLE_RADIUS + 2 : CIRCLE_RADIUS}
                    fill={circleColor}
                    stroke={isThisSelected ? '#fff' : '#1a1f2e'}
                    strokeWidth={isThisSelected ? 3 : 2}
                    opacity={selectedThemeId !== null && !isSelected ? 0.3 : 1}
                    className="cursor-pointer"
                    onClick={() => onCircleClick(theme.themeId, wp.week)}
                  />
                  {/* Paper count inside circle */}
                  <text
                    x={x}
                    y={y + 1}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="#1a1f2e"
                    fontSize="9"
                    fontWeight="bold"
                    className="pointer-events-none"
                  >
                    {wp.paperCount}
                  </text>
                </g>
              );
            })}

            {/* Theme label */}
            {(() => {
              const active = isActiveInLastWeek(theme);
              if (active) {
                const lastPoint = theme.weeklyPoints[theme.weeklyPoints.length - 1];
                const y = rankToY(lastPoint.rank);
                return (
                  <text
                    x={CHART_PADDING_LEFT + plotWidth + 12}
                    y={y}
                    dominantBaseline="middle"
                    fill={labelColor}
                    fontSize="11"
                    opacity={selectedThemeId !== null && !isSelected ? 0.3 : 0.9}
                  >
                    {theme.name.length > 35 ? theme.name.slice(0, 33) + '...' : theme.name}
                  </text>
                );
              } else {
                const firstPoint = theme.weeklyPoints[0];
                const y = rankToY(firstPoint.rank);
                return (
                  <text
                    x={CHART_PADDING_LEFT - 10}
                    y={y}
                    textAnchor="end"
                    dominantBaseline="middle"
                    fill={labelColor}
                    fontSize="11"
                    fontStyle="italic"
                    opacity={selectedThemeId !== null && !isSelected ? 0.3 : 0.6}
                  >
                    {theme.name.length > 25 ? theme.name.slice(0, 23) + '...' : theme.name}
                  </text>
                );
              }
            })()}
          </g>
        );
      })}
    </svg>
  );
}

// ============================================================================
// RENDER
// ============================================================================

export default function FrontiersPage() {
  const [data, setData] = useState<FrontiersData | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Selected circle state for showing paper table
  const [selectedThemeId, setSelectedThemeId] = useState<number | null>(null);
  const [selectedWeek, setSelectedWeek] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const result = await getFrontiersData();
        setData(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  /** Handles clicking a circle on the chart. Toggles selection. */
  const handleCircleClick = (themeId: number, week: string) => {
    if (selectedThemeId === themeId && selectedWeek === week) {
      setSelectedThemeId(null);
      setSelectedWeek(null);
    } else {
      setSelectedThemeId(themeId);
      setSelectedWeek(week);
    }
  };

  // Find the selected papers for the table
  const selectedPapers = useMemo((): { papers: FrontierPaper[]; themeName: string } | null => {
    if (selectedThemeId === null || selectedWeek === null || !data) return null;

    const theme = data.themes.find((t) => t.themeId === selectedThemeId);
    if (!theme) return null;

    const weekPoint = theme.weeklyPoints.find((wp) => wp.week === selectedWeek);
    if (!weekPoint) return null;

    return { papers: weekPoint.papers, themeName: theme.name };
  }, [data, selectedThemeId, selectedWeek]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">Loading research frontiers...</p>
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

  if (!data || data.themes.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <p className="text-gray-500">No research frontiers data found.</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold mb-2">Research Frontiers</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Research themes ranked by weekly paper count. Click a circle to see papers.
      </p>

      <ChartLegend />

      <div className="w-full overflow-x-auto">
        <BumpChart
          themes={data.themes}
          weeks={data.weeks}
          onCircleClick={handleCircleClick}
          selectedThemeId={selectedThemeId}
          selectedWeek={selectedWeek}
        />
      </div>

      {selectedPapers && selectedWeek && (
        <PaperTable
          papers={selectedPapers.papers}
          themeName={selectedPapers.themeName}
          week={selectedWeek}
        />
      )}
    </div>
  );
}
