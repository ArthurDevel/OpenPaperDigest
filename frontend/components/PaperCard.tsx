"use client";

import React, { useState } from 'react';
import type { MinimalPaperItem, Paper } from '../types/paper';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Share } from 'lucide-react';
import AddToListButtonMobile from './AddToListButtonMobile';
import CopyMarkdownButton from './CopyMarkdownButton';

// Preprocess backticked math expressions
const preprocessBacktickedMath = (src: string): string => {
  const looksMath = (s: string) => /[{}_^\\]|\\[a-zA-Z]+/.test(s);
  return (src || '').replace(/`([^`]+)`/g, (m, inner) => (looksMath(inner) ? `$${inner}$` : m));
};

interface PaperCardProps {
  paper: MinimalPaperItem;
  isExpanded: boolean;
  isLoadingSummary: boolean;
  summary?: Paper;
  onToggleExpand: (paperUuid: string) => void;
  onLoadSummary?: (paperUuid: string) => void;
}

export default function PaperCard({
  paper,
  isExpanded,
  isLoadingSummary,
  summary,
  onToggleExpand,
  onLoadSummary,
}: PaperCardProps) {
  const [copied, setCopied] = useState(false);

  // Handle share button click - always copy to clipboard
  const handleShare = async (e: React.MouseEvent) => {
    e.stopPropagation();

    if (!paper.slug) {
      console.warn('Paper has no slug, cannot share');
      return;
    }

    const shareUrl = `${window.location.origin}/paper/${paper.slug}`;

    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Error copying to clipboard:', err);
    }
  };

  const handleThumbnailClick = () => {
    onToggleExpand(paper.paper_uuid);
    if (!isExpanded && onLoadSummary) {
      onLoadSummary(paper.paper_uuid);
    }
  };

  return (
    <div
      id={`paper-${paper.paper_uuid}`}
      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm transition-all"
    >
      {/* Title and Authors */}
      <div className="p-4 pb-3">
        <h2 className="font-semibold text-lg text-gray-900 dark:text-gray-100 line-clamp-3">
          {paper.title || 'Untitled'}
        </h2>
        {paper.authors && (
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2 line-clamp-2">
            {paper.authors}
          </p>
        )}
      </div>

      {/* Thumbnail - always clickable */}
      <button
        onClick={handleThumbnailClick}
        className="w-full text-left"
      >
        <div className="w-full aspect-square bg-gray-100 dark:bg-gray-700 overflow-hidden hover:opacity-95 transition-opacity">
          {paper.thumbnail_url ? (
            <img
              src={paper.thumbnail_url}
              alt=""
              className="w-full h-full object-cover object-top"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">
              No thumbnail
            </div>
          )}
        </div>
      </button>

      {/* Summary Preview or Expanded Content */}
      {isLoadingSummary ? (
        <div className="border-t border-gray-200 dark:border-gray-700 px-4 py-3">
          <div className="text-gray-600 dark:text-gray-400 text-sm">
            Loading summary...
          </div>
        </div>
      ) : summary?.five_minute_summary ? (
        isExpanded ? (
          // Fully expanded
          <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-900/50 relative">
            <div className="mb-3 flex items-center gap-2">
              <span className="inline-block px-2 py-0.5 text-xs font-medium rounded bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300">
                5-Minute Summary
              </span>
              {summary.arxiv_url && (
                <a
                  href={summary.arxiv_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
                  onClick={(e) => e.stopPropagation()}
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                  arXiv
                </a>
              )}
            </div>
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkMath]}
                rehypePlugins={[rehypeKatex]}
              >
                {preprocessBacktickedMath(summary.five_minute_summary)}
              </ReactMarkdown>
            </div>
            {/* Action buttons - bottom right corner when expanded */}
            <div className="mt-4 flex items-center justify-end gap-2">
              <CopyMarkdownButton paperUuid={paper.paper_uuid} fiveMinuteSummary={summary?.five_minute_summary} />
              <AddToListButtonMobile paperId={paper.paper_uuid} paperTitle={paper.title || undefined} />

              {paper.slug && (
                <button
                  onClick={handleShare}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-blue-500 dark:border-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors text-blue-600 dark:text-blue-400 text-xs"
                  title="Share this paper"
                  aria-label="Share this paper"
                >
                  {copied ? (
                    <span className="text-green-600 dark:text-green-400 font-medium">Copied</span>
                  ) : (
                    <>
                      <Share className="w-4 h-4" />
                      <span>Share</span>
                    </>
                  )}
                </button>
              )}
            </div>
          </div>
        ) : (
          // Preview with fade-out
          <button
            onClick={handleThumbnailClick}
            className="w-full text-left border-t border-gray-200 dark:border-gray-700 px-4 pb-4 pt-3 relative group"
          >
            <div className="relative overflow-hidden" style={{ maxHeight: '10rem' }}>
              <div className="prose prose-sm dark:prose-invert max-w-none text-gray-700 dark:text-gray-300">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm, remarkMath]}
                  rehypePlugins={[rehypeKatex]}
                >
                  {preprocessBacktickedMath(summary.five_minute_summary)}
                </ReactMarkdown>
              </div>
              {/* Fade overlay */}
              <div className="absolute bottom-0 left-0 right-0 h-20 bg-gradient-to-t from-white dark:from-gray-800 to-transparent pointer-events-none group-hover:from-gray-50 dark:group-hover:from-gray-700 transition-colors" />
            </div>
            <div className="mt-2 text-xs text-blue-600 dark:text-blue-400 group-hover:underline">
              Click to read more
            </div>
          </button>
        )
      ) : null}
    </div>
  );
}
