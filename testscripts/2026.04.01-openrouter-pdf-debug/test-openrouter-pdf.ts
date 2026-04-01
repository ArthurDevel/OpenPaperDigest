/**
 * OpenRouter PDF Debug Script (TypeScript / standalone)
 *
 * Investigates why OpenRouter returns "Provider returned error" (400) for
 * certain arxiv PDFs when using google/gemini-3-flash-preview with URL-based
 * file_data.
 *
 * Responsibilities:
 * - Tests URL-based PDF submission for a FAILING and a WORKING paper
 * - Downloads the failing PDF locally and tests base64-encoded submission
 * - Logs full request payloads (API key redacted) and full responses
 * - Prints a pass/fail summary for each test
 *
 * Run: npx tsx test-openrouter-pdf.ts
 */

import { config } from "dotenv";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

config(); // load .env

// ============================================================================
// CONSTANTS
// ============================================================================

const __dirname = dirname(fileURLToPath(import.meta.url));
const INPUT_DIR = resolve(__dirname, "input");

const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";
const MODEL = "google/gemini-3-flash-preview";
const SYSTEM_PROMPT = "Summarize this paper briefly in 2-3 sentences.";
const USER_TEXT = "Please summarize this research paper.";
const DELAY_BETWEEN_CALLS_MS = 2000;

interface Paper {
  label: string;
  arxivId: string;
  pdfUrl: string;
}

interface TestResult {
  testName: string;
  success: boolean;
  durationMs: number;
  detail: string;
}

const FAILING_PAPER: Paper = {
  label: "FAILING",
  arxivId: "2601.02350",
  pdfUrl: "https://arxiv.org/pdf/2601.02350",
};

const WORKING_PAPER: Paper = {
  label: "WORKING",
  arxivId: "2603.07602",
  pdfUrl: "https://arxiv.org/pdf/2603.07602",
};

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

async function main(): Promise<void> {
  console.log("=== OpenRouter PDF Debug Script ===\n");

  const apiKey = getApiKey();
  console.log(`API key loaded (${apiKey.substring(0, 15)}...)\n`);

  mkdirSync(INPUT_DIR, { recursive: true });

  const results: TestResult[] = [];

  // Test 1: URL-based -- FAILING paper
  console.log("TEST 1: URL-based file_data -- FAILING paper");
  const result1 = await runUrlTest(apiKey, FAILING_PAPER);
  results.push(result1);

  await delay(DELAY_BETWEEN_CALLS_MS);

  // Test 2: URL-based -- WORKING paper
  console.log("\nTEST 2: URL-based file_data -- WORKING paper");
  const result2 = await runUrlTest(apiKey, WORKING_PAPER);
  results.push(result2);

  await delay(DELAY_BETWEEN_CALLS_MS);

  // Test 3: Base64-based -- FAILING paper (download first, then encode)
  console.log("\nTEST 3: Base64-based file_data -- FAILING paper (downloaded locally)");
  const result3 = await runBase64Test(apiKey, FAILING_PAPER);
  results.push(result3);

  // Summary
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
 * Reads OPENROUTER_API_KEY from the environment (loaded via dotenv).
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
 * Builds the request payload using a PDF URL (matches the app's format exactly).
 * @param pdfUrl - URL pointing to the PDF
 * @returns The request body object
 */
function buildUrlPayload(pdfUrl: string): object {
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
 * Builds the request payload using a base64-encoded data URI.
 * @param base64DataUri - data:application/pdf;base64,... string
 * @returns The request body object
 */
function buildBase64Payload(base64DataUri: string): object {
  return {
    model: MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: USER_TEXT },
          { type: "file", file: { filename: "paper.pdf", file_data: base64DataUri } },
        ],
      },
    ],
    plugins: [{ id: "file-parser", pdf: { engine: "native" } }],
  };
}

/**
 * Sends a payload to OpenRouter and logs the full request/response.
 * @param apiKey - OpenRouter API key
 * @param payload - The request body
 * @param testName - Label for this test
 * @returns A TestResult with success/failure info
 */
async function callOpenRouter(
  apiKey: string,
  payload: object,
  testName: string
): Promise<TestResult> {
  // Log the request payload with the API key redacted
  const redactedPayload = JSON.parse(JSON.stringify(payload));
  console.log(`  Request payload:\n${JSON.stringify(redactedPayload, null, 2)}\n`);

  const start = Date.now();

  const response = await fetch(OPENROUTER_API_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://papersummarizer.test",
      "X-Title": "PDF Debug Script",
    },
    body: JSON.stringify(payload),
  });

  const durationMs = Date.now() - start;
  const responseBody = await response.json();

  // Log the full response
  console.log(`  HTTP status: ${response.status}`);
  console.log(`  Full response:\n${JSON.stringify(responseBody, null, 2)}\n`);

  // Determine success: check both HTTP status and error field in body
  const hasError = !response.ok || responseBody.error;

  if (hasError) {
    const errorMsg = responseBody.error?.message || `HTTP ${response.status}`;
    console.log(`  RESULT: FAILED -- ${errorMsg} (${durationMs}ms)`);
    return { testName, success: false, durationMs, detail: errorMsg };
  }

  const content: string = responseBody.choices?.[0]?.message?.content || "(empty)";
  const truncated = content.length > 300 ? content.substring(0, 300) + "..." : content;
  console.log(`  RESULT: SUCCESS (${durationMs}ms)`);
  console.log(`  Summary: "${truncated}"`);
  return { testName, success: true, durationMs, detail: truncated };
}

/**
 * Runs the URL-based test for a given paper.
 * @param apiKey - OpenRouter API key
 * @param paper - Paper info (label, arxivId, pdfUrl)
 * @returns TestResult
 */
async function runUrlTest(apiKey: string, paper: Paper): Promise<TestResult> {
  const payload = buildUrlPayload(paper.pdfUrl);
  const testName = `URL | ${paper.label} (${paper.arxivId})`;
  return callOpenRouter(apiKey, payload, testName);
}

/**
 * Downloads the PDF to input/, base64-encodes it, and sends as data URI.
 * @param apiKey - OpenRouter API key
 * @param paper - Paper info
 * @returns TestResult
 */
async function runBase64Test(apiKey: string, paper: Paper): Promise<TestResult> {
  const testName = `Base64 | ${paper.label} (${paper.arxivId})`;
  const localPath = resolve(INPUT_DIR, `${paper.arxivId}.pdf`);

  // Download the PDF
  console.log(`  Downloading ${paper.pdfUrl} ...`);
  const downloadResponse = await fetch(paper.pdfUrl);
  if (!downloadResponse.ok) {
    const msg = `Failed to download PDF: HTTP ${downloadResponse.status}`;
    console.log(`  ${msg}`);
    return { testName, success: false, durationMs: 0, detail: msg };
  }

  const buffer = Buffer.from(await downloadResponse.arrayBuffer());
  writeFileSync(localPath, buffer);

  const sizeKb = (buffer.length / 1024).toFixed(1);
  console.log(`  Saved to ${localPath} (${sizeKb} KB)`);

  // Validate PDF header
  const header = buffer.subarray(0, 5).toString("ascii");
  console.log(`  PDF header: "${header}" (${header === "%PDF-" ? "valid" : "INVALID"})\n`);

  // Base64-encode and send
  const base64 = buffer.toString("base64");
  const dataUri = `data:application/pdf;base64,${base64}`;

  // Log a truncated version of the payload (base64 is huge)
  console.log(`  Base64 data URI length: ${dataUri.length} chars`);
  const payload = buildBase64Payload(dataUri);
  return callOpenRouter(apiKey, payload, testName);
}

/**
 * Prints a summary table of all test results.
 * @param results - Array of TestResult objects
 */
function printSummary(results: TestResult[]): void {
  console.log("\n============================================================");
  console.log("SUMMARY");
  console.log("============================================================");

  for (const r of results) {
    const status = r.success ? "OK" : "FAIL";
    console.log(`  [${status}] ${r.testName} (${r.durationMs}ms)`);
  }

  console.log("============================================================\n");
}
