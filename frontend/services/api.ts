import { JobStatusResponse, Paper, type MinimalPaperItem, type PaginatedMinimalPapers } from '../types/paper';

export const API_URL = '/api'; // The backend is on port 8000, but we're proxying, see next.config.js for dev, and /api/[...slug] for prod.

export const processPaper = async (file: File): Promise<JobStatusResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_URL}/papers/process`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    return response.json();
};

export const getJobStatus = async (jobId: string): Promise<Paper | null> => {
    const response = await fetch(`${API_URL}/papers/process/${jobId}`);

    if (response.status === 202) {
        // Job is still processing, return null to indicate polling should continue
        return null;
    }
    
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }

    // Job is complete, return the final result
    return response.json();
}

export type EnqueueArxivResponse = {
    job_db_id: number;
    paper_uuid: string;
    status: string;
}

export const enqueueArxiv = async (url: string): Promise<EnqueueArxivResponse> => {
    const response = await fetch(`${API_URL}/papers/enqueue_arxiv`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ url }),
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export type JobDbStatus = {
    paper_uuid: string;
    status: string;
    error_message?: string | null;
    created_at: string;
    updated_at: string;
    started_at?: string | null;
    finished_at?: string | null;
    arxiv_id: string;
    arxiv_version?: string | null;
    arxiv_url?: string | null;
    title?: string | null;
    authors?: string | null;
    num_pages?: number | null;
    thumbnail_data_url?: string | null;
    processing_time_seconds?: number | null;
    total_cost?: number | null;
    avg_cost_per_page?: number | null;
}

export const listPapers = async (status?: string): Promise<JobDbStatus[]> => {
    const url = new URL(`${API_URL}/admin/papers`, window.location.origin);
    if (status) url.searchParams.set('status', status);
    const response = await fetch(url.toString());
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export type RequestedPaper = {
    arxiv_id: string;
    arxiv_abs_url: string;
    arxiv_pdf_url: string;
    request_count: number;
    first_requested_at: string;
    last_requested_at: string;
    title?: string | null;
    authors?: string | null;
    num_pages?: number | null;
}

export const listRequestedPapers = async (): Promise<RequestedPaper[]> => {
    const response = await fetch(`${API_URL}/admin/requested_papers`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export const startProcessingRequested = async (arxivIdOrUrl: string): Promise<{ paper_uuid: string; status: string; }> => {
    const encoded = encodeURIComponent(arxivIdOrUrl);
    const response = await fetch(`${API_URL}/admin/requested_papers/${encoded}/start_processing`, { method: 'POST' });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export const deleteRequestedPaper = async (arxivIdOrUrl: string): Promise<{ deleted: string }> => {
    const encoded = encodeURIComponent(arxivIdOrUrl);
    const response = await fetch(`${API_URL}/admin/requested_papers/${encoded}`, { method: 'DELETE' });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export const listMinimalPapers = async (): Promise<MinimalPaperItem[]> => {
    const response = await fetch(`${API_URL}/papers/minimal`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export const listMinimalPapersPaginated = async (page: number, limit: number): Promise<PaginatedMinimalPapers> => {
    const url = new URL(`${API_URL}/papers/minimal`, window.location.origin);
    url.searchParams.set('page', page.toString());
    url.searchParams.set('limit', limit.toString());
    const response = await fetch(url.toString());
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

export const fetchPaperMarkdown = async (paperUuid: string): Promise<string> => {
    const response = await fetch(`${API_URL}/papers/${paperUuid}/markdown`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    const data = await response.json();
    return data.final_markdown;
}

export const fetchPaperSummary = async (paperUuid: string): Promise<Paper> => {
    const response = await fetch(`${API_URL}/papers/${paperUuid}/summary`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

// --- Public: check paper existence by arXiv ID ---
export type CheckArxivResponse = {
    exists: boolean;
    viewer_url?: string | null;
};

export const checkArxiv = async (arxivIdOrUrl: string): Promise<CheckArxivResponse> => {
    // Reject pre-encoded inputs to avoid double-encoding issues
    if (/%[0-9A-Fa-f]{2}/.test(arxivIdOrUrl)) {
        throw new Error('checkArxiv received an already-encoded value; pass a raw arXiv id or URL');
    }
    const encoded = encodeURIComponent(arxivIdOrUrl);
    const response = await fetch(`${API_URL}/papers/check_arxiv/${encoded}`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
};

// --- Public: request paper for processing ---

export type ArxivAuthor = {
    name: string;
    affiliation?: string | null;
};

export type ArxivMetadata = {
    arxiv_id: string;
    latest_version?: string | null;
    title: string;
    authors: ArxivAuthor[];
    summary: string;
    categories: string[];
    doi?: string | null;
    journal_ref?: string | null;
    submitted_at?: string | null;
    updated_at?: string | null;
};

export const getArxivMetadata = async (arxivIdOrUrl: string): Promise<ArxivMetadata> => {
    const encoded = encodeURIComponent(arxivIdOrUrl);
    const response = await fetch(`${API_URL}/arxiv-metadata/${encoded}`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
};

// Removed: EmailNotification types and listing API; notifications feature deprecated

// --- Search APIs ---

export type SearchQueryRequest = {
    query: string;
    is_new?: boolean;
    selected_categories?: string[] | null;
    date_from?: string | null;
    date_to?: string | null;
    limit?: number;
};

export type SearchItem = {
    paper_uuid: string;
    slug?: string | null;
    title?: string | null;
    authors?: string | null;
    published?: string | null;
    abs_url?: string | null;
    summary?: string | null;
    qdrant_score?: number | null;
    rerank_score?: number | null;
};

export type SearchQueryResponse = {
    items: SearchItem[];
    rewritten_query?: string | null;
    applied_categories?: string[] | null;
    applied_date_from?: string | null;
    applied_date_to?: string | null;
};

export const searchPapers = async (payload: SearchQueryRequest): Promise<SearchQueryResponse> => {
    const response = await fetch(`${API_URL}/search/query`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

// --- Admin: Cumulative daily papers count ---
export type CumulativeDailyPaperItem = {
    date: string;
    daily_count: number;
    cumulative_count: number;
    cumulative_failed: number;
    cumulative_processed: number;
    cumulative_not_started: number;
    cumulative_processing: number;
};

export const getCumulativeDailyPapers = async (): Promise<CumulativeDailyPaperItem[]> => {
    const response = await fetch(`${API_URL}/admin/papers/cumulative_daily`);
    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
    }
    return response.json();
}

