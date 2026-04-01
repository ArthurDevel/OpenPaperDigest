/**
 * Bulk OpenRouter PDF Test Script
 *
 * Tests a batch of 10 arxiv PDFs via OpenRouter to measure how many fail
 * with "Provider returned error".
 *
 * Responsibilities:
 * - Sends each arxiv PDF URL to OpenRouter sequentially (2s delay between calls)
 * - Logs HTTP status, error/success, and duration for each paper
 * - Prints a pass/fail summary table at the end
 *
 * Run: npx tsx test-bulk-papers.ts
 */

import { config } from "dotenv";

config(); // load .env

// ============================================================================
// CONSTANTS
// ============================================================================

const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";
const MODEL = "google/gemini-3-flash-preview";
const SYSTEM_PROMPT = "Summarize this paper in one sentence.";
const USER_TEXT = "Please summarize this research paper.";
const DELAY_BETWEEN_CALLS_MS = 2000;

const ARXIV_IDS: string[] = [
  "2601.02350", // known failing
  "2603.07602", // known working
  "2603.10773",
  "2603.11802",
  "2601.08665",
  "2601.16276",
  "2603.09778",
  "2603.09465",
  "2603.09435",
  "2603.10145",
];

// ============================================================================
// INTERFACES
// ============================================================================

interface TestResult {
  arxivId: string;
  httpStatus: number;
  hasChoices: boolean;
  hasError: boolean;
  errorMessage: string;
  durationMs: number;
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

async function main(): Promise<void> {
  console.log("=== Bulk OpenRouter PDF Test ===\n");

  const apiKey = getApiKey();
  console.log(`API key loaded (${apiKey.substring(0, 15)}...)`);
  console.log(`Testing ${ARXIV_IDS.length} papers sequentially\n`);

  const results: TestResult[] = [];

  for (let i = 0; i < ARXIV_IDS.length; i++) {
    const arxivId = ARXIV_IDS[i];
    console.log(`[${i + 1}/${ARXIV_IDS.length}] Testing ${arxivId} ...`);

    const result = await testPaper(apiKey, arxivId);
    results.push(result);

    const status = result.hasError ? "FAIL" : "PASS";
    console.log(
      `  -> ${status} | HTTP ${result.httpStatus} | ${result.durationMs}ms` +
        (result.hasError ? ` | ${result.errorMessage}` : " | has choices")
    );

    // Delay before next call (skip after last)
    if (i < ARXIV_IDS.length - 1) {
      await delay(DELAY_BETWEEN_CALLS_MS);
    }
  }

  printSummary(results);
}

main().catch((err) => {
  console.error("\nFatal error:", err);
  process.exit(1);
});

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Reads OPENROUTER_API_KEY from the environment.
 * @returns The API key string
 */
function getApiKey(): string {
  const key = process.env.OPENROUTER_API_KEY;
  if (!key) {
    throw new Error("OPENROUTER_API_KEY is not set. Check your .env file.");
  }
  return key;
}

/**
 * Waits for a given number of milliseconds.
 * @param ms - milliseconds to wait
 */
function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Builds the OpenRouter request payload for a given arxiv PDF URL.
 * @param pdfUrl - Full URL to the arxiv PDF
 * @returns The request body object
 */
function buildPayload(pdfUrl: string): object {
  return {
    model: MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: USER_TEXT },
          { type: "file", file: { filename: "paper.pdf", file_data: pdfUrl } },
        ],
      },
    ],
    plugins: [{ id: "file-parser", pdf: { engine: "native" } }],
  };
}

/**
 * Sends a single arxiv paper to OpenRouter and returns the result.
 * @param apiKey - OpenRouter API key
 * @param arxivId - The arxiv paper ID (e.g. "2601.02350")
 * @returns TestResult with status, timing, and error info
 */
async function testPaper(apiKey: string, arxivId: string): Promise<TestResult> {
  const pdfUrl = `https://arxiv.org/pdf/${arxivId}`;
  const payload = buildPayload(pdfUrl);

  const start = Date.now();

  const response = await fetch(OPENROUTER_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://papersummarizer.test",
      "X-Title": "PDF Bulk Test Script",
    },
    body: JSON.stringify(payload),
  });

  const durationMs = Date.now() - start;
  const body = await response.json();

  const hasError = !response.ok || !!body.error;
  const hasChoices = !!body.choices && body.choices.length > 0;
  const errorMessage = body.error?.message || "";

  return {
    arxivId,
    httpStatus: response.status,
    hasChoices,
    hasError,
    errorMessage,
    durationMs,
  };
}

/**
 * Prints a summary table of all test results.
 * @param results - Array of TestResult objects
 */
function printSummary(results: TestResult[]): void {
  const passed = results.filter((r) => !r.hasError);
  const failed = results.filter((r) => r.hasError);

  console.log("\n============================================================");
  console.log("SUMMARY TABLE");
  console.log("============================================================");
  console.log(
    `${"arxiv_id".padEnd(16)} ${"status".padEnd(8)} ${"HTTP".padEnd(6)} ${"time".padEnd(10)} detail`
  );
  console.log("-".repeat(70));

  for (const r of results) {
    const status = r.hasError ? "FAIL" : "PASS";
    const detail = r.hasError ? r.errorMessage : "choices returned";
    console.log(
      `${r.arxivId.padEnd(16)} ${status.padEnd(8)} ${String(r.httpStatus).padEnd(6)} ${(r.durationMs + "ms").padEnd(10)} ${detail}`
    );
  }

  console.log("-".repeat(70));
  console.log(`PASSED: ${passed.length}/${results.length}  |  FAILED: ${failed.length}/${results.length}`);
  console.log("============================================================\n");
}
