/**
 * Score Breakdown Badge and Detail Modal
 *
 * Displays a small score pill on expanded paper cards. Clicking opens a modal
 * with a detailed breakdown of how the paper was scored and why it was shown.
 *
 * Responsibilities:
 * - Render a compact score badge with the total score
 * - Render a modal with per-component score bars, context, and explanation text
 */

"use client";

import React, { useState } from 'react';
import type { ScoreBreakdown } from '@/types/recommendation';

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Formats an ISO date string as a relative time description (e.g. "3 days ago").
 * @param isoDate - ISO 8601 date string
 * @returns Human-readable relative time
 */
function formatRelativeDate(isoDate: string): string {
  const diffMs = Date.now() - new Date(isoDate).getTime();
  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (days === 0) return 'today';
  if (days === 1) return '1 day ago';
  if (days < 30) return `${days} days ago`;
  if (days < 365) {
    const months = Math.floor(days / 30);
    return months === 1 ? '1 month ago' : `${months} months ago`;
  }
  const years = Math.floor(days / 365);
  return years === 1 ? '1 year ago' : `${years} years ago`;
}

/**
 * Returns a short description for the recency score given the publish date.
 * @param recencyScore - Normalized recency score (0-1)
 * @param finishedAt - ISO date of when the paper was processed
 * @returns Description string
 */
function getRecencyDetail(recencyScore: number, finishedAt: string): string {
  const relative = formatRelativeDate(finishedAt);
  const date = new Date(finishedAt).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });

  if (recencyScore > 0.8) return `Published ${date} (${relative}). Very recent -- strong recency boost.`;
  if (recencyScore > 0.4) return `Published ${date} (${relative}). Moderate recency.`;
  return `Published ${date} (${relative}). Older paper -- recency score is low.`;
}

/**
 * Returns a short description for the author popularity score.
 * @param authorPopularityScore - Normalized author popularity score (0-1)
 * @param maxAuthorHIndex - Raw max h-index value or null
 * @returns Description string
 */
function getAuthorPopularityDetail(authorPopularityScore: number, maxAuthorHIndex: number | null): string {
  if (maxAuthorHIndex === null || maxAuthorHIndex === 0) {
    return 'No author h-index data available. Score is 0.';
  }
  if (maxAuthorHIndex >= 50) {
    return `Max author h-index: ${maxAuthorHIndex} (capped at max score). Highly cited authors.`;
  }
  return `Max author h-index: ${maxAuthorHIndex}. Score = h-index / 50.`;
}

/**
 * Returns a short description for the HuggingFace upvotes score.
 * @param hfUpvotesScore - Normalized HF upvotes score (0-1)
 * @param upvotes - Raw HuggingFace upvote count or null
 * @returns Description string
 */
function getHfUpvotesDetail(hfUpvotesScore: number, upvotes: number | null): string {
  if (upvotes === null) {
    return 'No HuggingFace upvote data available. Score is 0.';
  }
  if (upvotes >= 100) return `${upvotes} HuggingFace upvotes (capped at max score).`;
  if (upvotes > 0) return `${upvotes} HuggingFace upvotes. Score = upvotes / 100.`;
  return '0 HuggingFace upvotes.';
}

/**
 * Returns a short description for the similarity score.
 * @param breakdown - The full score breakdown
 * @returns Description string
 */
function getSimilarityDetail(breakdown: ScoreBreakdown): string {
  if (breakdown.isExploration) {
    return 'Exploration paper -- not matched to your interests. Similarity is 0.';
  }

  if (breakdown.sourceClusterIndex !== null) {
    return `Cosine similarity to your interest cluster #${breakdown.sourceClusterIndex + 1}, boosted by cluster weight.`;
  }

  if (breakdown.similarityScore === 0) {
    return 'No personalization data yet. Similarity is 0 (cold start).';
  }

  return `Similarity score: ${breakdown.similarityScore.toFixed(3)}.`;
}

/**
 * Returns a top-level explanation of why this paper is in the feed.
 * @param breakdown - The score breakdown for the paper
 * @returns Explanation string
 */
function getExplanation(breakdown: ScoreBreakdown): string {
  if (breakdown.isExploration) {
    return 'This paper was added for topic discovery -- it is outside your usual reading interests so you can explore new areas. It scores on popularity and recency only.';
  }

  if (breakdown.sourceClusterIndex !== null) {
    return `Matched to your interest cluster #${breakdown.sourceClusterIndex + 1}. Score = 0.33 x similarity + 0.33 x author popularity + 0.33 x recency + 0.33 x HF upvotes (capped at 1.0).`;
  }

  return 'Ranked by author popularity, recency, and HF upvotes only (no personalization data yet).';
}

// ============================================================================
// COMPONENTS
// ============================================================================

/**
 * A single score row with a label, bar, value, and detail text.
 */
function ScoreRow({
  label,
  value,
  color,
  detail,
}: {
  label: string;
  value: number;
  color: string;
  detail: string;
}) {
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
        <span>{label}</span>
        <span>{value.toFixed(3)}</span>
      </div>
      <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${color} rounded-full transition-all`}
          style={{ width: `${Math.min(value * 100, 100)}%` }}
        />
      </div>
      <p className="text-[11px] text-gray-500 dark:text-gray-500 mt-1 leading-snug">
        {detail}
      </p>
    </div>
  );
}

/**
 * Modal showing detailed score breakdown with bars, context, and explanation.
 */
function ScoreDetailModal({
  breakdown,
  onClose,
}: {
  breakdown: ScoreBreakdown;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-sm w-full mx-4 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Score Breakdown
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-lg leading-none"
          >
            x
          </button>
        </div>

        {/* Total score */}
        <div className="mb-4 text-center">
          <span className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            {breakdown.score.toFixed(3)}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-1">total</span>
        </div>

        {/* Component rows with detail text */}
        <div className="space-y-4 mb-4">
          <ScoreRow
            label="Similarity"
            value={breakdown.similarityScore}
            color="bg-blue-500"
            detail={getSimilarityDetail(breakdown)}
          />
          <ScoreRow
            label="Author Popularity"
            value={breakdown.authorPopularityScore}
            color="bg-amber-500"
            detail={getAuthorPopularityDetail(breakdown.authorPopularityScore, breakdown.maxAuthorHIndex)}
          />
          <ScoreRow
            label="Recency"
            value={breakdown.recencyScore}
            color="bg-green-500"
            detail={getRecencyDetail(breakdown.recencyScore, breakdown.finishedAt)}
          />
          <ScoreRow
            label="HF Upvotes"
            value={breakdown.hfUpvotesScore}
            color="bg-rose-500"
            detail={getHfUpvotesDetail(breakdown.hfUpvotesScore, breakdown.upvotes)}
          />
        </div>

        {/* Exploration tag */}
        {breakdown.isExploration && (
          <div className="mb-3">
            <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300">
              Exploration
            </span>
          </div>
        )}

        {/* Explanation */}
        <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">
          {getExplanation(breakdown)}
        </p>

        {/* Note about scoring */}
        <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-3 leading-snug">
          Score = 0.33 x each term, capped at 1.0. Author popularity uses max h-index (Semantic Scholar). HF upvotes from HuggingFace Daily Papers.
        </p>
      </div>
    </div>
  );
}

/**
 * Compact badge showing total score. Clicking opens the detail modal.
 * @param breakdown - The score breakdown for the paper
 */
export default function ScoreBreakdownBadge({ breakdown }: { breakdown: ScoreBreakdown }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setIsOpen(true);
        }}
        className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        title="View score breakdown"
      >
        {breakdown.isExploration ? (
          <span className="text-purple-600 dark:text-purple-400">explore</span>
        ) : (
          <span>{breakdown.score.toFixed(2)}</span>
        )}
      </button>

      {isOpen && (
        <ScoreDetailModal
          breakdown={breakdown}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
