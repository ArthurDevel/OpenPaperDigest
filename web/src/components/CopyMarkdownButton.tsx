'use client';

import React, { useState } from 'react';
import { Check, Copy } from 'lucide-react';
// COMMENTED OUT: "Copy Full Document" depends on content.md which v2 pipeline papers don't have.
// This was too expensive to regenerate for v2. Bring back once we have an affordable alternative.
// import { fetchPaperMarkdown } from '../services/api';

type CopyMarkdownButtonProps = {
  paperUuid: string;
  fiveMinuteSummary?: string | null;
};

export default function CopyMarkdownButton({ paperUuid: _paperUuid, fiveMinuteSummary }: CopyMarkdownButtonProps) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCopySummary = async () => {
    if (!fiveMinuteSummary) {
      setError('Summary not available');
      return;
    }

    setError(null);

    try {
      await navigator.clipboard.writeText(fiveMinuteSummary);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy summary:', err);
      setError('Failed to copy to clipboard');
    }
  };

  // COMMENTED OUT: "Copy Full Document" depends on content.md which v2 pipeline papers don't have.
  // This was too expensive to regenerate for v2. Bring back once we have an affordable alternative.
  // const handleCopyFullDocument = async () => {
  //   setError(null);
  //   setLoading(true);
  //
  //   try {
  //     const markdown = await fetchPaperMarkdown(paperUuid);
  //     await navigator.clipboard.writeText(markdown);
  //     setCopied('full');
  //     setTimeout(() => setCopied(null), 2000);
  //     setIsOpen(false);
  //   } catch (err: any) {
  //     if (err.message.includes('404')) {
  //       setError('Original markdown not available for this paper');
  //     } else {
  //       setError('Failed to copy to clipboard');
  //     }
  //   } finally {
  //     setLoading(false);
  //   }
  // };

  return (
    <div className="relative z-50">
      <button
        onClick={handleCopySummary}
        disabled={!fiveMinuteSummary}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300 text-xs disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {copied ? (
          <>
            <Check className="w-4 h-4 text-green-600 dark:text-green-400" />
            <span className="text-green-600 dark:text-green-400 font-medium">Copied</span>
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            <span>Copy Summary</span>
          </>
        )}
      </button>

      {/* COMMENTED OUT: "Copy Full Document" depends on content.md which v2 pipeline papers don't have.
          This was too expensive to regenerate for v2. Bring back once we have an affordable alternative.
      {isOpen && !loading && !copied && (
        <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-lg z-50">
          <div className="py-1">
            <button
              onClick={handleCopySummary}
              disabled={!fiveMinuteSummary}
              className="w-full text-left px-4 py-2 text-sm text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              <Copy className="w-4 h-4" />
              Copy Summary
            </button>
            <button
              onClick={handleCopyFullDocument}
              className="w-full text-left px-4 py-2 text-sm text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2"
            >
              <Copy className="w-4 h-4" />
              Copy Full Document
            </button>
          </div>
        </div>
      )}
      */}

      {error && (
        <div className="absolute right-0 mt-2 w-64 p-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 rounded text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
