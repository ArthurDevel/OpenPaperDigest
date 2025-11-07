'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Check, Copy, Loader, ChevronDown } from 'lucide-react';
import { fetchPaperMarkdown } from '../services/api';

type CopyMarkdownButtonProps = {
  paperUuid: string;
  fiveMinuteSummary?: string | null;
};

export default function CopyMarkdownButton({ paperUuid, fiveMinuteSummary }: CopyMarkdownButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState<'summary' | 'full' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const copyToClipboard = async (text: string): Promise<void> => {
    await navigator.clipboard.writeText(text);
  };

  const handleCopySummary = async () => {
    console.log('handleCopySummary called');
    if (!fiveMinuteSummary) {
      console.log('No summary available');
      setError('Summary not available');
      return;
    }

    setError(null);

    try {
      console.log('Copying summary to clipboard...');
      await copyToClipboard(fiveMinuteSummary);
      console.log('Summary copied successfully');
      setCopied('summary');
      setTimeout(() => setCopied(null), 2000);
      setIsOpen(false);
    } catch (err) {
      console.error('Failed to copy summary:', err);
      setError('Failed to copy to clipboard');
    }
  };

  const handleCopyFullDocument = async () => {
    console.log('handleCopyFullDocument called');
    setError(null);
    setLoading(true);

    try {
      console.log('Fetching markdown for paper:', paperUuid);
      const markdown = await fetchPaperMarkdown(paperUuid);
      console.log('Markdown fetched, length:', markdown.length);
      await copyToClipboard(markdown);
      console.log('Full document copied successfully');
      setCopied('full');
      setTimeout(() => setCopied(null), 2000);
      setIsOpen(false);
    } catch (err: any) {
      console.error('Failed to copy full document:', err);
      if (err.message.includes('404')) {
        setError('Original markdown not available for this paper');
      } else {
        setError('Failed to copy to clipboard');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative z-50" ref={dropdownRef}>
      <button
        onClick={() => {
          console.log('CopyMarkdownButton clicked! Current isOpen:', isOpen);
          setIsOpen(!isOpen);
          console.log('Setting isOpen to:', !isOpen);
        }}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300 text-xs"
        disabled={loading}
      >
        {copied ? (
          <span className="text-green-600 dark:text-green-400 font-medium">Copied</span>
        ) : loading ? (
          <>
            <Loader className="w-4 h-4 animate-spin" />
            <span>Loading...</span>
          </>
        ) : (
          <>
            <Copy className="w-4 h-4" />
            <span>Markdown</span>
            <ChevronDown className="w-3 h-3" />
          </>
        )}
      </button>

      {(() => {
        console.log('Dropdown render check - isOpen:', isOpen, 'loading:', loading, 'copied:', copied);
        console.log('Should render dropdown:', isOpen && !loading && !copied);
        return null;
      })()}

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

      {error && (
        <div className="absolute right-0 mt-2 w-64 p-2 bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 rounded text-xs">
          {error}
        </div>
      )}
    </div>
  );
}
