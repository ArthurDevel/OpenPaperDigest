/**
 * Test script to check arxiv PDF download sizes and behavior.
 *
 * For each arxiv ID, performs a HEAD request to check:
 * - Content-Length (file size)
 * - Content-Type
 * - Redirect behavior
 * - Final URL
 * - Response status
 *
 * Hypothesis: large PDFs fail because OpenRouter times out downloading them.
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const ARXIV_BASE_URL = "https://arxiv.org/pdf";

interface ArxivTestCase {
  arxivId: string;
  failedViaUrl: boolean;
}

interface PdfSizeResult {
  arxivId: string;
  failedViaUrl: boolean;
  status: number;
  contentLength: number | null;
  contentType: string | null;
  redirected: boolean;
  finalUrl: string;
  error: string | null;
}

const TEST_CASES: ArxivTestCase[] = [
  { arxivId: "2601.02350", failedViaUrl: true },
  { arxivId: "2603.07602", failedViaUrl: false },
  { arxivId: "2603.10773", failedViaUrl: false },
  { arxivId: "2603.11802", failedViaUrl: false },
  { arxivId: "2601.08665", failedViaUrl: false },
  { arxivId: "2601.16276", failedViaUrl: false },
  { arxivId: "2603.09778", failedViaUrl: false },
  { arxivId: "2603.09465", failedViaUrl: true },
  { arxivId: "2603.09435", failedViaUrl: false },
  { arxivId: "2603.10145", failedViaUrl: false },
];

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

async function main(): Promise<void> {
  console.log("Checking arxiv PDF sizes and download behavior...\n");

  const results: PdfSizeResult[] = [];

  for (const testCase of TEST_CASES) {
    const result = await checkPdfSize(testCase);
    results.push(result);

    const sizeStr = result.contentLength
      ? formatBytes(result.contentLength)
      : "unknown";
    const label = result.failedViaUrl ? "FAIL" : "PASS";
    console.log(`[${label}] ${result.arxivId} - ${sizeStr} - status ${result.status}`);
  }

  printSummaryTable(results);
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Performs a HEAD request to the arxiv PDF URL and collects metadata.
 * @param testCase - the arxiv ID and whether it failed via URL
 * @returns PdfSizeResult with all collected metadata
 */
async function checkPdfSize(testCase: ArxivTestCase): Promise<PdfSizeResult> {
  const url = `${ARXIV_BASE_URL}/${testCase.arxivId}`;

  try {
    const response = await fetch(url, {
      method: "HEAD",
      redirect: "follow",
    });

    const contentLength = response.headers.get("content-length");
    const contentType = response.headers.get("content-type");

    return {
      arxivId: testCase.arxivId,
      failedViaUrl: testCase.failedViaUrl,
      status: response.status,
      contentLength: contentLength ? parseInt(contentLength, 10) : null,
      contentType,
      redirected: response.redirected,
      finalUrl: response.url,
      error: null,
    };
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : String(err);
    return {
      arxivId: testCase.arxivId,
      failedViaUrl: testCase.failedViaUrl,
      status: 0,
      contentLength: null,
      contentType: null,
      redirected: false,
      finalUrl: url,
      error: errorMessage,
    };
  }
}

/**
 * Formats byte count into a human-readable string (KB or MB).
 * @param bytes - raw byte count
 * @returns formatted string like "1.23 MB"
 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Prints a summary table of results sorted by file size (descending).
 * @param results - array of PdfSizeResult to display
 */
function printSummaryTable(results: PdfSizeResult[]): void {
  const sorted = [...results].sort((a, b) => {
    const sizeA = a.contentLength ?? 0;
    const sizeB = b.contentLength ?? 0;
    return sizeB - sizeA;
  });

  console.log("\n" + "=".repeat(100));
  console.log("SUMMARY TABLE (sorted by file size, largest first)");
  console.log("=".repeat(100));
  console.log(
    padRight("ArxivID", 16) +
    padRight("URL Result", 12) +
    padRight("Size", 14) +
    padRight("Content-Type", 24) +
    padRight("Status", 8) +
    padRight("Redirected", 12) +
    "Final URL"
  );
  console.log("-".repeat(100));

  for (const r of sorted) {
    const sizeStr = r.contentLength ? formatBytes(r.contentLength) : r.error ?? "unknown";
    const label = r.failedViaUrl ? "FAIL" : "PASS";

    console.log(
      padRight(r.arxivId, 16) +
      padRight(label, 12) +
      padRight(sizeStr, 14) +
      padRight(r.contentType ?? "n/a", 24) +
      padRight(String(r.status), 8) +
      padRight(r.redirected ? "yes" : "no", 12) +
      r.finalUrl
    );
  }

  console.log("=".repeat(100));

  // Print analysis
  const failedSizes = sorted
    .filter((r) => r.failedViaUrl && r.contentLength)
    .map((r) => r.contentLength!);
  const passedSizes = sorted
    .filter((r) => !r.failedViaUrl && r.contentLength)
    .map((r) => r.contentLength!);

  if (failedSizes.length > 0 && passedSizes.length > 0) {
    const avgFailed = failedSizes.reduce((a, b) => a + b, 0) / failedSizes.length;
    const avgPassed = passedSizes.reduce((a, b) => a + b, 0) / passedSizes.length;
    const maxPassed = Math.max(...passedSizes);
    const minFailed = Math.min(...failedSizes);

    console.log("\nANALYSIS:");
    console.log(`  Average size of FAILED PDFs: ${formatBytes(avgFailed)}`);
    console.log(`  Average size of PASSED PDFs: ${formatBytes(avgPassed)}`);
    console.log(`  Largest PASSED PDF:          ${formatBytes(maxPassed)}`);
    console.log(`  Smallest FAILED PDF:         ${formatBytes(minFailed)}`);

    if (minFailed > maxPassed) {
      console.log("\n  --> CONFIRMED: All failed PDFs are larger than all passed PDFs.");
      console.log("  --> This supports the hypothesis that large PDFs cause OpenRouter timeouts.");
    } else {
      console.log("\n  --> Size alone does NOT explain the failures.");
      console.log("  --> The hypothesis that large PDFs cause timeouts is NOT confirmed.");
    }
  }
}

/**
 * Pads a string to the right with spaces.
 * @param str - input string
 * @param len - desired total length
 * @returns padded string
 */
function padRight(str: string, len: number): string {
  return str.length >= len ? str : str + " ".repeat(len - str.length);
}

main().catch(console.error);
