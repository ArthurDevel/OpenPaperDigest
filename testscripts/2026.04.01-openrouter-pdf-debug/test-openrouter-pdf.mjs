/**
 * OpenRouter PDF Debug Script
 *
 * Investigates why OpenRouter returns "Provider returned error (400)" for some
 * arxiv papers but not others when using google/gemini-3-flash-preview.
 *
 * Responsibilities:
 * - Downloads two PDFs (one failing, one working) and validates them
 * - Tests URL-based file_data for both papers
 * - Tests base64 file_data as a workaround for the failing paper
 * - Tests without the plugins field for the failing paper
 * - Prints a summary table of results
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// ============================================================================
// CONSTANTS
// ============================================================================

const __dirname = dirname(fileURLToPath(import.meta.url));
const INPUT_DIR = resolve(__dirname, "input");
const ENV_PATH = resolve(__dirname, ".env");

const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";
const MODEL = "google/gemini-3-flash-preview";
const SYSTEM_PROMPT = "Summarize this paper in one sentence.";
const USER_TEXT = "Please summarize this research paper.";
const DELAY_MS = 2000;

const PAPERS = {
  failing: {
    label: "FAILING",
    arxivId: "2601.02350",
    uuid: "09a925e8-96aa-46e3-908b-d014f76d15e7",
    pdfUrl: "https://arxiv.org/pdf/2601.02350",
  },
  working: {
    label: "WORKING",
    arxivId: "2603.07602",
    uuid: "933b39b3-ecbb-43c7-8fee-db78ab83b540",
    pdfUrl: "https://arxiv.org/pdf/2603.07602",
  },
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/** Reads the .env file and extracts OPENROUTER_API_KEY */
function loadApiKey() {
  if (!existsSync(ENV_PATH)) {
    throw new Error(`.env file not found at ${ENV_PATH}. Copy .env.example to .env and add your key.`);
  }
  const content = readFileSync(ENV_PATH, "utf-8");
  const match = content.match(/^OPENROUTER_API_KEY=(.+)$/m);
  if (!match || !match[1].trim()) {
    throw new Error("OPENROUTER_API_KEY not found in .env file.");
  }
  return match[1].trim();
}

/** Downloads a PDF from a URL and saves it to the input folder. Returns the file path. */
async function downloadPdf(paper) {
  const filePath = resolve(INPUT_DIR, `${paper.arxivId}.pdf`);

  console.log(`  Downloading ${paper.pdfUrl} ...`);
  const response = await fetch(paper.pdfUrl);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} downloading ${paper.pdfUrl}`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  writeFileSync(filePath, buffer);

  const sizeKb = (buffer.length / 1024).toFixed(1);
  console.log(`  Saved to ${filePath} (${sizeKb} KB)`);

  // Validate PDF magic bytes
  const header = buffer.subarray(0, 5).toString("ascii");
  const isValid = header === "%PDF-";
  console.log(`  PDF magic bytes: "${header}" -> ${isValid ? "VALID" : "INVALID"}`);

  return { filePath, sizeBytes: buffer.length, isValid };
}

/** Waits for a given number of milliseconds */
function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Calls OpenRouter with the given payload and returns a result object.
 * @param {string} apiKey - The API key
 * @param {object} payload - The request body
 * @param {string} testLabel - Label for logging
 * @returns {{ success: boolean, durationMs: number, summary: string }}
 */
async function callOpenRouter(apiKey, payload, testLabel) {
  console.log(`\n--- ${testLabel} ---`);
  console.log(`  Model: ${payload.model}`);
  console.log(`  Plugins: ${payload.plugins ? JSON.stringify(payload.plugins) : "none"}`);

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
  const json = await response.json();

  if (!response.ok || json.error) {
    console.log(`  FAILED (${response.status}) in ${durationMs}ms`);
    console.log(`  Response: ${JSON.stringify(json, null, 2)}`);
    return {
      success: false,
      durationMs,
      summary: json.error?.message || `HTTP ${response.status}`,
    };
  }

  const content = json.choices?.[0]?.message?.content || "";
  const truncated = content.length > 200 ? content.substring(0, 200) + "..." : content;
  console.log(`  SUCCESS in ${durationMs}ms`);
  console.log(`  Response: "${truncated}"`);
  console.log(`  Usage: ${JSON.stringify(json.usage)}`);

  return { success: true, durationMs, summary: truncated };
}

/**
 * Builds the standard OpenRouter payload for a PDF via URL.
 * @param {string} pdfUrl - URL to the PDF
 * @param {boolean} includePlugins - Whether to include the file-parser plugin
 */
function buildUrlPayload(pdfUrl, includePlugins = true) {
  const payload = {
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
  };
  if (includePlugins) {
    payload.plugins = [{ id: "file-parser", pdf: { engine: "native" } }];
  }
  return payload;
}

/**
 * Builds the OpenRouter payload for a PDF via base64 data URI.
 * @param {string} filePath - Path to the local PDF file
 */
function buildBase64Payload(filePath) {
  const pdfBuffer = readFileSync(filePath);
  const base64 = pdfBuffer.toString("base64");
  const dataUri = `data:application/pdf;base64,${base64}`;

  return {
    model: MODEL,
    messages: [
      { role: "system", content: SYSTEM_PROMPT },
      {
        role: "user",
        content: [
          { type: "text", text: USER_TEXT },
          { type: "file", file: { filename: "paper.pdf", file_data: dataUri } },
        ],
      },
    ],
    plugins: [{ id: "file-parser", pdf: { engine: "native" } }],
  };
}

/** Prints the summary table of all test results */
function printSummaryTable(results) {
  console.log("\n\n============================================================");
  console.log("SUMMARY TABLE");
  console.log("============================================================");

  const labelWidth = 50;
  const statusWidth = 10;
  const timeWidth = 10;

  const header =
    "Test".padEnd(labelWidth) + "Status".padEnd(statusWidth) + "Time".padEnd(timeWidth);
  console.log(header);
  console.log("-".repeat(labelWidth + statusWidth + timeWidth));

  for (const r of results) {
    const status = r.success ? "OK" : "FAIL";
    const time = `${r.durationMs}ms`;
    const line = r.label.padEnd(labelWidth) + status.padEnd(statusWidth) + time.padEnd(timeWidth);
    console.log(line);
  }

  console.log("============================================================\n");
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

async function main() {
  console.log("=== OpenRouter PDF Debug Script ===\n");

  const apiKey = loadApiKey();
  console.log(`API key loaded (${apiKey.substring(0, 15)}...)\n`);

  // Step 1: Download both PDFs
  console.log("STEP 1: Download PDFs\n");
  mkdirSync(INPUT_DIR, { recursive: true });

  const failingPdf = await downloadPdf(PAPERS.failing);
  const workingPdf = await downloadPdf(PAPERS.working);

  if (!failingPdf.isValid) console.log("\n  WARNING: Failing paper PDF has invalid header!");
  if (!workingPdf.isValid) console.log("\n  WARNING: Working paper PDF has invalid header!");

  console.log(`\n  Size comparison: failing=${failingPdf.sizeBytes} bytes, working=${workingPdf.sizeBytes} bytes`);

  const results = [];

  // Step 2: Test URL-based file_data for both papers
  console.log("\n\nSTEP 2: Test URL-based file_data (with plugins)");

  try {
    const payload = buildUrlPayload(PAPERS.failing.pdfUrl, true);
    const result = await callOpenRouter(apiKey, payload, `URL + plugins | ${PAPERS.failing.label} (${PAPERS.failing.arxivId})`);
    results.push({ label: `URL + plugins | FAILING (${PAPERS.failing.arxivId})`, ...result });
  } catch (err) {
    console.log(`  ERROR: ${err.message}`);
    results.push({ label: `URL + plugins | FAILING (${PAPERS.failing.arxivId})`, success: false, durationMs: 0, summary: err.message });
  }

  await delay(DELAY_MS);

  try {
    const payload = buildUrlPayload(PAPERS.working.pdfUrl, true);
    const result = await callOpenRouter(apiKey, payload, `URL + plugins | ${PAPERS.working.label} (${PAPERS.working.arxivId})`);
    results.push({ label: `URL + plugins | WORKING (${PAPERS.working.arxivId})`, ...result });
  } catch (err) {
    console.log(`  ERROR: ${err.message}`);
    results.push({ label: `URL + plugins | WORKING (${PAPERS.working.arxivId})`, success: false, durationMs: 0, summary: err.message });
  }

  await delay(DELAY_MS);

  // Step 3: Test base64 file_data for failing paper
  console.log("\n\nSTEP 3: Test base64 file_data for FAILING paper");

  try {
    const payload = buildBase64Payload(failingPdf.filePath);
    const result = await callOpenRouter(apiKey, payload, `Base64 + plugins | ${PAPERS.failing.label} (${PAPERS.failing.arxivId})`);
    results.push({ label: `Base64 + plugins | FAILING (${PAPERS.failing.arxivId})`, ...result });
  } catch (err) {
    console.log(`  ERROR: ${err.message}`);
    results.push({ label: `Base64 + plugins | FAILING (${PAPERS.failing.arxivId})`, success: false, durationMs: 0, summary: err.message });
  }

  await delay(DELAY_MS);

  // Step 4: Test without plugins for failing paper (URL mode)
  console.log("\n\nSTEP 4: Test URL without plugins for FAILING paper");

  try {
    const payload = buildUrlPayload(PAPERS.failing.pdfUrl, false);
    const result = await callOpenRouter(apiKey, payload, `URL no plugins | ${PAPERS.failing.label} (${PAPERS.failing.arxivId})`);
    results.push({ label: `URL no plugins | FAILING (${PAPERS.failing.arxivId})`, ...result });
  } catch (err) {
    console.log(`  ERROR: ${err.message}`);
    results.push({ label: `URL no plugins | FAILING (${PAPERS.failing.arxivId})`, success: false, durationMs: 0, summary: err.message });
  }

  // Step 5: Print summary
  printSummaryTable(results);
}

main().catch((err) => {
  console.error("\nFatal error:", err.message);
  process.exit(1);
});
