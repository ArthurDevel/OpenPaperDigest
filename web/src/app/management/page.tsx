"use client";

import { useEffect, useState } from 'react';
import { listPapers, listRequestedPapers, deleteRequestedPaper, enqueueArxiv, type JobDbStatus, type RequestedPaper } from '../../services/api';
import Link from 'next/link';

export default function ManagementPage() {
  const [dbPapers, setDbPapers] = useState<JobDbStatus[]>([]);
  const [requested, setRequested] = useState<RequestedPaper[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [processingUuid, setProcessingUuid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openMenuUuid, setOpenMenuUuid] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setIsLoading(true);
        setError(null);
        // Load DB-backed papers list
        const dbList = await listPapers();
        setDbPapers(dbList);
        // Load requested papers
        const requestedList = await listRequestedPapers();
        setRequested(requestedList);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  const onImportJson = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.onchange = async () => {
      if (!input.files || input.files.length === 0) return;
      const file = input.files[0];
      try {
        setIsLoading(true);
        setError(null);
        const text = await file.text();
        // Validate JSON locally first
        const parsed = JSON.parse(text);
        // Import into backend (writes DB row and data/paperjsons file)
        const res = await fetch('/api/admin/papers/import_json', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(parsed),
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload?.detail || `Import failed (${res.status})`);
        // Refresh DB list
        const dbList = await listPapers();
        setDbPapers(dbList);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Invalid JSON file');
      } finally {
        setIsLoading(false);
      }
    };
    input.click();
  };

  const onAddArxiv = async () => {
    const url = prompt('Enter arXiv URL (e.g., https://arxiv.org/abs/xxxx.xxxxx)');
    if (!url) return;
    try {
      setIsLoading(true);
      setError(null);
      const payload = await enqueueArxiv(url);
      alert(`Enqueued. Paper UUID: ${payload.paperUuid}. It will appear once processed.`);
      const dbList = await listPapers();
      setDbPapers(dbList);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to enqueue');
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMenu = (uuid: string) => {
    setOpenMenuUuid((prev) => (prev === uuid ? null : uuid));
  };

  return (
    <div className="px-6 py-6 text-gray-900 dark:text-gray-100">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Management</h1>
        <div className="flex items-center gap-3">
          <Link
            href="/management/papers-overview"
            className="px-4 py-2 rounded-md bg-green-600 text-white hover:bg-green-700 transition-colors"
          >
            Papers Overview
          </Link>
          <button
            onClick={onImportJson}
            className="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            Import JSON
          </button>
          <button
            onClick={onAddArxiv}
            className="px-4 py-2 rounded-md bg-gray-800 text-white hover:bg-gray-900 transition-colors"
          >
            Add Arxiv URL
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md border border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/40 dark:text-red-300">
          {error}
        </div>
      )}

      {isLoading ? (
        <div>Loading…</div>
      ) : (
        <>
          <div className="mb-6 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm">
            <div className="px-6 py-3 text-sm font-semibold border-b border-gray-2 00 dark:border-gray-700">Requested Papers</div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">arXiv ID</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Title</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Authors</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Pages</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Abs URL</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">PDF URL</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Requests</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">First</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Last</th>
                    <th className="px-6 py-3" />
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {requested.map((r) => (
                    <tr key={r.arxivId} className={processingUuid === r.arxivId ? 'opacity-60' : ''}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        {processingUuid === r.arxivId && <span className="inline-block animate-spin mr-2">⟳</span>}
                        {r.arxivId}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm max-w-md truncate" title={r.title || ''}>{r.title || '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm max-w-md truncate" title={r.authors || ''}>{r.authors || '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{typeof r.numPages === 'number' ? r.numPages : '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <a href={r.arxivAbsUrl} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">Abs</a>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <a href={r.arxivPdfUrl} className="text-blue-600 hover:underline" target="_blank" rel="noopener noreferrer">PDF</a>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{r.requestCount}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.firstRequestedAt}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.lastRequestedAt}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                        <div className="inline-flex items-center gap-2">
                          <button
                            className="px-3 py-1 rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                            disabled={processingUuid !== null}
                            onClick={async () => {
                              try {
                                setProcessingUuid(r.arxivId);
                                setError(null);
                                // Start processing via API
                                await fetch(`/api/admin/requested_papers/${encodeURIComponent(r.arxivId)}/start_processing`, { method: 'POST' });
                                // Refresh lists
                                const [dbList, reqList] = await Promise.all([
                                  listPapers(),
                                  listRequestedPapers(),
                                ]);
                                setDbPapers(dbList);
                                setRequested(reqList);
                              } catch (e) {
                                setError(e instanceof Error ? e.message : 'Failed to start processing');
                              } finally {
                                setProcessingUuid(null);
                              }
                            }}
                          >
                            {processingUuid === r.arxivId ? '⟳' : 'Start'}
                          </button>
                          <div className="relative inline-block text-left">
                            <Menu arxivId={r.arxivId} disabled={processingUuid !== null} onDeleted={async () => {
                              try {
                                setProcessingUuid(r.arxivId);
                                setError(null);
                                await deleteRequestedPaper(r.arxivId);
                                const reqList = await listRequestedPapers();
                                setRequested(reqList);
                              } catch (e) {
                                setError(e instanceof Error ? e.message : 'Failed to delete request');
                              } finally {
                                setProcessingUuid(null);
                              }
                            }} />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {requested.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">No requests yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
          <div className="mb-6 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg shadow-sm">
            <div className="px-6 py-3 text-sm font-semibold border-b border-gray-200 dark:border-gray-700">Papers (Database)</div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-700/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Title</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Authors</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">ArXiv ID</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Paper UUID</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Status</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Pages</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Proc. Time (s)</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Total Cost ($)</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Avg/Page ($)</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">ArXiv Abs</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">ArXiv PDF</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Created</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Started</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Finished</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Error</th>
                    <th className="px-6 py-3" />
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {dbPapers.map((r) => (
                    <tr key={r.paperUuid} className={processingUuid === r.paperUuid ? 'opacity-60' : ''}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium max-w-xs truncate" title={r.title || ''}>
                        {processingUuid === r.paperUuid && <span className="inline-block animate-spin mr-2">⟳</span>}
                        {r.title || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400 max-w-sm truncate" title={r.authors || ''}>{r.authors || '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">{r.arxivId}{r.arxivVersion || ''}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.paperUuid}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{r.status}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{r.numPages ?? '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{typeof r.processingTimeSeconds === 'number' ? r.processingTimeSeconds.toFixed(2) : '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{typeof r.totalCost === 'number' ? r.totalCost.toFixed(4) : '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">{typeof r.avgCostPerPage === 'number' ? r.avgCostPerPage.toFixed(5) : '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <a
                          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                          href={`https://arxiv.org/abs/${r.arxivId}${r.arxivVersion || ''}`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Abs
                        </a>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <a
                          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                          href={`https://arxiv.org/pdf/${r.arxivId}${r.arxivVersion || ''}.pdf`}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          PDF
                        </a>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.createdAt}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.startedAt || '-'}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">{r.finishedAt || '-'}</td>
                      <td className="px-6 py-4 text-sm text-red-600 dark:text-red-400 max-w-xs truncate" title={r.errorMessage || ''}>{r.errorMessage || ''}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm relative">
                        <button
                          className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                          disabled={processingUuid !== null}
                          onClick={() => toggleMenu(r.paperUuid)}
                          aria-label="Actions"
                          title="Actions"
                        >
                          ⋮
                        </button>
                        {openMenuUuid === r.paperUuid && (
                          <div className="absolute right-0 mt-2 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg z-10">
                            <button
                              className="block w-full text-left px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                              disabled={processingUuid !== null}
                              onClick={async () => {
                                try {
                                  setProcessingUuid(r.paperUuid);
                                  setError(null);
                                  const filename = `${r.paperUuid}.json`;
                                  const res = await fetch(`/layouttests/data?file=${encodeURIComponent(filename)}`, { cache: 'no-store' });
                                  const payload = await res.json().catch(() => ({}));
                                  if (!res.ok) throw new Error(payload?.error || `Download failed (${res.status})`);
                                  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
                                  const url = URL.createObjectURL(blob);
                                  const a = document.createElement('a');
                                  a.href = url;
                                  a.download = filename;
                                  document.body.appendChild(a);
                                  a.click();
                                  a.remove();
                                  URL.revokeObjectURL(url);
                                } catch (e) {
                                  setError(e instanceof Error ? e.message : 'Failed to download');
                                } finally {
                                  setProcessingUuid(null);
                                  setOpenMenuUuid(null);
                                }
                              }}
                            >
                              Download JSON
                            </button>
                            <button
                              className="block w-full text-left px-4 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                              disabled={processingUuid !== null}
                              onClick={async () => {
                                try {
                                  setProcessingUuid(r.paperUuid);
                                  setError(null);
                                  const res = await fetch(`/api/admin/papers/${encodeURIComponent(r.paperUuid)}/restart`, { method: 'POST' });
                                  if (!res.ok) {
                                    const payload = await res.json().catch(() => ({}));
                                    throw new Error(payload?.detail || `Restart failed (${res.status})`);
                                  }
                                  const dbList = await listPapers();
                                  setDbPapers(dbList);
                                } catch (e) {
                                  setError(e instanceof Error ? e.message : 'Failed to restart');
                                } finally {
                                  setProcessingUuid(null);
                                  setOpenMenuUuid(null);
                                }
                              }}
                            >
                              Restart
                            </button>
                            <button
                              className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                              disabled={processingUuid !== null}
                              onClick={async () => {
                                try {
                                  if (!confirm('Delete this paper? This will also delete the JSON file.')) return;
                                  setProcessingUuid(r.paperUuid);
                                  setError(null);
                                  const res = await fetch(`/api/admin/papers/${encodeURIComponent(r.paperUuid)}`, { method: 'DELETE' });
                                  if (!res.ok) {
                                    const payload = await res.json().catch(() => ({}));
                                    throw new Error(payload?.detail || `Delete failed (${res.status})`);
                                  }
                                  const dbList = await listPapers();
                                  setDbPapers(dbList);
                                } catch (e) {
                                  setError(e instanceof Error ? e.message : 'Failed to delete');
                                } finally {
                                  setProcessingUuid(null);
                                  setOpenMenuUuid(null);
                                }
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                  {dbPapers.length === 0 && (
                    <tr>
                      <td colSpan={13} className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                        No papers found in database.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Menu({ arxivId, disabled, onDeleted }: { arxivId: string; disabled: boolean; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        className="px-2 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        title="Actions"
      >
        ⋮
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-40 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg z-10">
          <button
            className="block w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={disabled}
            onClick={async () => {
              setOpen(false);
              if (!confirm(`Delete request for ${arxivId}?`)) return;
              await onDeleted();
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}


