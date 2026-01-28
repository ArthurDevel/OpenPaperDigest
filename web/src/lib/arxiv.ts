/**
 * arXiv API Client
 *
 * Provides utilities for working with arXiv paper identifiers and metadata.
 * - Parses and normalizes arXiv URLs and IDs (both old and new style)
 * - Fetches paper metadata from the arXiv Atom API
 * - Constructs PDF URLs for arXiv papers
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const ARXIV_HOST = 'https://arxiv.org';
const ARXIV_EXPORT_HOST = 'http://export.arxiv.org';
const TIMEOUT_MS = 60000;
const USER_AGENT = 'papersummarizer/0.1 (+https://arxiv.org)';

// Regex patterns for arXiv ID formats
// New style: 1234.56789 or 1234.56789v1
const NEW_STYLE_RE = /^(?<id>\d{4}\.\d{4,5})(?<ver>v\d+)?$/;
// Old style: hep-th/9901001 or hep-th/9901001v2
const OLD_STYLE_RE = /^(?<id>[a-z-]+(?:\.[A-Z]{2})?\/\d{7})(?<ver>v\d+)?$/i;

// ============================================================================
// TYPES
// ============================================================================

/**
 * Normalized arXiv identifier with optional version.
 */
export interface NormalizedArxivId {
  arxivId: string;
  version: string | null;
}

/**
 * Metadata for an arXiv paper fetched from the API.
 */
export interface ArxivMetadata {
  arxivId: string;
  title: string;
  authors: string[];
  abstract: string;
  publishedAt: Date;
  categories: string[];
}

/**
 * Parsed components of an arXiv URL or ID.
 */
interface ParsedArxivUrl {
  raw: string;
  arxivId: string;
  version: string | null;
  urlType: 'id' | 'abs' | 'pdf';
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Splits an arXiv identifier into base ID and version components.
 * @param idOrVersioned - The arXiv ID string, possibly with version suffix
 * @returns Tuple of [baseId, version or null]
 * @throws Error if the identifier format is not recognized
 */
function splitIdAndVersion(idOrVersioned: string): [string, string | null] {
  // Try new style first
  let match = NEW_STYLE_RE.exec(idOrVersioned);
  if (match?.groups) {
    return [match.groups.id, match.groups.ver || null];
  }

  // Try old style
  match = OLD_STYLE_RE.exec(idOrVersioned);
  if (match?.groups) {
    return [match.groups.id, match.groups.ver || null];
  }

  // Clean up common variations and retry
  let cleaned = idOrVersioned.trim();
  if (cleaned.endsWith('.pdf')) {
    cleaned = cleaned.slice(0, -4);
  }
  if (cleaned.toLowerCase().startsWith('arxiv:')) {
    cleaned = cleaned.split(':', 2)[1];
  }

  // One more attempt after cleaning
  match = NEW_STYLE_RE.exec(cleaned) || OLD_STYLE_RE.exec(cleaned);
  if (match?.groups) {
    return [match.groups.id, match.groups.ver || null];
  }

  throw new Error(`Unrecognized arXiv identifier: ${idOrVersioned}`);
}

/**
 * Parses an arXiv URL or raw identifier into components.
 * @param url - URL or raw arXiv ID string
 * @returns Parsed URL components
 * @throws Error if the format is not recognized
 */
function parseUrl(url: string): ParsedArxivUrl {
  const raw = url.trim();

  // Accept raw IDs or arXiv:ID format
  if (!raw.startsWith('http://') && !raw.startsWith('https://')) {
    const [arxivId, version] = splitIdAndVersion(raw);
    return { raw, arxivId, version, urlType: 'id' };
  }

  // Parse URL path
  const pathMatch = /^https?:\/\/[^/]+\/(.+)$/.exec(raw);
  if (!pathMatch) {
    throw new Error('Invalid arXiv URL');
  }
  const path = pathMatch[1];

  // Match /abs/<id>(vN)[optional slash] with optional query/fragment
  const absMatch = /^abs\/(?<idver>[^/?#]+)(?:\/)?(?:[?#].*)?$/.exec(path);
  if (absMatch?.groups) {
    const [arxivId, version] = splitIdAndVersion(absMatch.groups.idver);
    return { raw, arxivId, version, urlType: 'abs' };
  }

  // Match /pdf/<id>(vN)[.pdf optional][optional slash] with optional query/fragment
  const pdfMatch = /^pdf\/(?<idver>[^/?#]+?)(?:\.pdf)?(?:\/)?(?:[?#].*)?$/.exec(path);
  if (pdfMatch?.groups) {
    const [arxivId, version] = splitIdAndVersion(pdfMatch.groups.idver);
    return { raw, arxivId, version, urlType: 'pdf' };
  }

  throw new Error('Unsupported arXiv URL format');
}

/**
 * Extracts text content from an XML element by tag name with namespace.
 * @param element - Parent XML element
 * @param tagName - Tag name to find (without namespace prefix)
 * @param namespace - XML namespace URI
 * @returns Text content or null if not found
 */
function findText(element: Element, tagName: string, namespace: string): string | null {
  const found = element.getElementsByTagNameNS(namespace, tagName)[0];
  return found?.textContent?.trim() || null;
}

/**
 * Constructs the PDF download URL for an arXiv paper.
 * @param arxivId - The arXiv paper ID
 * @param version - Optional version suffix (e.g., "v1")
 * @returns The full PDF URL
 */
export function buildPdfUrl(arxivId: string, version?: string | null): string {
  const suffix = version || '';
  return `${ARXIV_HOST}/pdf/${arxivId}${suffix}.pdf`;
}

// ============================================================================
// MAIN EXPORTS
// ============================================================================

/**
 * Parses an arXiv URL or ID string into a normalized form.
 * Handles various input formats including:
 * - Raw IDs: "2301.12345", "hep-th/9901001"
 * - Versioned IDs: "2301.12345v2"
 * - arXiv: prefix: "arXiv:2301.12345"
 * - Full URLs: "https://arxiv.org/abs/2301.12345"
 *
 * @param urlOrId - The arXiv URL or identifier to normalize
 * @returns Normalized arXiv ID and optional version
 * @throws Error if the input format is not recognized
 */
export function normalizeId(urlOrId: string): NormalizedArxivId {
  const parsed = parseUrl(urlOrId);
  return {
    arxivId: parsed.arxivId,
    version: parsed.version,
  };
}

/**
 * Fetches paper metadata from the arXiv Atom API.
 *
 * @param arxivId - The arXiv paper ID (e.g., "2301.12345")
 * @returns Paper metadata including title, authors, abstract, etc.
 * @throws Error if the paper is not found or the API request fails
 */
export async function fetchMetadata(arxivId: string): Promise<ArxivMetadata> {
  const queryUrl = `${ARXIV_EXPORT_HOST}/api/query?id_list=${encodeURIComponent(arxivId)}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(queryUrl, {
      headers: { 'User-Agent': USER_AGENT },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    throw new Error(`arXiv API request failed: ${response.status} ${response.statusText}`);
  }

  const xmlText = await response.text();

  // Parse Atom XML
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, 'application/xml');

  // Check for parse errors
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    throw new Error('Failed to parse arXiv API response');
  }

  const atomNs = 'http://www.w3.org/2005/Atom';
  const entry = doc.getElementsByTagNameNS(atomNs, 'entry')[0];

  if (!entry) {
    throw new Error(`No metadata found for arXiv ID: ${arxivId}`);
  }

  // Extract fields
  const title = findText(entry, 'title', atomNs) || '';
  const abstract = findText(entry, 'summary', atomNs) || '';
  const publishedStr = findText(entry, 'published', atomNs);

  // Parse authors
  const authorElements = entry.getElementsByTagNameNS(atomNs, 'author');
  const authors: string[] = [];
  for (let i = 0; i < authorElements.length; i++) {
    const name = findText(authorElements[i], 'name', atomNs);
    if (name) {
      authors.push(name);
    }
  }

  // Parse categories
  const categoryElements = entry.getElementsByTagNameNS(atomNs, 'category');
  const categories: string[] = [];
  for (let i = 0; i < categoryElements.length; i++) {
    const term = categoryElements[i].getAttribute('term');
    if (term) {
      categories.push(term);
    }
  }

  // Parse published date
  let publishedAt: Date;
  if (publishedStr) {
    publishedAt = new Date(publishedStr);
    if (isNaN(publishedAt.getTime())) {
      throw new Error(`Invalid published date: ${publishedStr}`);
    }
  } else {
    throw new Error('Missing published date in arXiv metadata');
  }

  return {
    arxivId,
    title: title.replace(/\s+/g, ' ').trim(), // Normalize whitespace in title
    authors,
    abstract: abstract.replace(/\s+/g, ' ').trim(),
    publishedAt,
    categories,
  };
}
