/**
 * Bulk PDF test script for OpenRouter's file-parser plugin.
 *
 * Downloads 15 arxiv PDFs, sends each through OpenRouter's PDF URL pipeline,
 * and reports whether file size correlates with failure.
 *
 * Responsibilities:
 * - Download arxiv PDFs in parallel (staggered) and record sizes
 * - Send each PDF URL to OpenRouter sequentially and record results
 * - Print a summary table and save results as JSON
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ============================================================================
// CONSTANTS
// ============================================================================

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV_PATH = path.join(__dirname, ".env");
const INPUT_DIR = path.join(__dirname, "input");
const OUTPUT_DIR = path.join(__dirname, "output");

const ARXIV_IDS = [
  "2603.07602",
  "2603.10773",
  "2603.11802",
  "2601.08665",
  "2601.02350",
  "2603.09778",
  "2601.16276",
  "2603.09465",
  "2603.09435",
  "2603.10145",
  "2603.08448",
  "2603.09235",
  "2603.10305",
  "2603.09332",
  "2603.11048",
];

const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
const OPENROUTER_MODEL = "google/gemini-3-flash-preview";
const DOWNLOAD_STAGGER_MS = 200;
const REQUEST_DELAY_MS = 3000;
const PDF_MAGIC_BYTES = Buffer.from([0x25, 0x50, 0x44, 0x46]); // %PDF

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Reads the OPENROUTER_API_KEY from a .env file in the script directory.
 * @returns {string} The API key
 */
function loadApiKey() {
  if (!fs.existsSync(ENV_PATH)) {
    throw new Error(`Missing .env file at ${ENV_PATH}`);
  }
  const content = fs.readFileSync(ENV_PATH, "utf-8");
  const match = content.match(/^OPENROUTER_API_KEY=(.+)$/m);
  if (!match) {
    throw new Error("OPENROUTER_API_KEY not found in .env file");
  }
  return match[1].trim();
}

/**
 * Waits for a given number of milliseconds.
 * @param {number} ms - Milliseconds to wait
 * @returns {Promise<void>}
 */
function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Downloads a single arxiv PDF to the input folder.
 * @param {string} arxivId - The arxiv paper ID
 * @returns {Promise<{arxivId: string, sizeBytes: number, sizeKB: number, valid: boolean}>}
 */
async function downloadPdf(arxivId) {
  const url = `https://arxiv.org/pdf/${arxivId}`;
  const filePath = path.join(INPUT_DIR, `${arxivId.replace("/", "_")}.pdf`);

  console.log(`  Downloading ${arxivId}...`);
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download ${arxivId}: HTTP ${response.status}`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  fs.writeFileSync(filePath, buffer);

  const sizeBytes = buffer.length;
  const sizeKB = Math.round(sizeBytes / 1024);
  const valid = buffer.subarray(0, 4).equals(PDF_MAGIC_BYTES);

  console.log(`  ${arxivId}: ${sizeKB} KB, valid PDF: ${valid}`);
  return { arxivId, sizeBytes, sizeKB, valid };
}

/**
 * Tests a single paper against the OpenRouter PDF URL pipeline.
 * @param {string} arxivId - The arxiv paper ID
 * @param {string} apiKey - OpenRouter API key
 * @returns {Promise<{arxivId: string, status: string, timeSeconds: number, error: string|null, response: string|null}>}
 */
async function testOpenRouterPdf(arxivId, apiKey) {
  const pdfUrl = `https://arxiv.org/pdf/${arxivId}`;
  const payload = {
    model: OPENROUTER_MODEL,
    messages: [
      {
        role: "system",
        content: "Respond with exactly one sentence summarizing this paper.",
      },
      {
        role: "user",
        content: [
          { type: "text", text: "Summarize this paper." },
          {
            type: "file",
            file: { filename: "paper.pdf", file_data: pdfUrl },
          },
        ],
      },
    ],
    plugins: [{ id: "file-parser", pdf: { engine: "native" } }],
  };

  const start = Date.now();
  try {
    const response = await fetch(OPENROUTER_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const elapsed = (Date.now() - start) / 1000;
    const body = await response.json();

    if (!response.ok || body.error) {
      const errorMsg =
        body.error?.message || `HTTP ${response.status}`;
      console.log(`  ${arxivId}: FAIL (${elapsed.toFixed(1)}s) - ${errorMsg}`);
      return {
        arxivId,
        status: "FAIL",
        timeSeconds: elapsed,
        error: errorMsg,
        response: null,
      };
    }

    const content = body.choices?.[0]?.message?.content || "";
    console.log(`  ${arxivId}: OK (${elapsed.toFixed(1)}s)`);
    return {
      arxivId,
      status: "OK",
      timeSeconds: elapsed,
      error: null,
      response: content,
    };
  } catch (err) {
    const elapsed = (Date.now() - start) / 1000;
    console.log(`  ${arxivId}: FAIL (${elapsed.toFixed(1)}s) - ${err.message}`);
    return {
      arxivId,
      status: "FAIL",
      timeSeconds: elapsed,
      error: err.message,
      response: null,
    };
  }
}

/**
 * Pads a string to a given width for table formatting.
 * @param {string} str - The string to pad
 * @param {number} width - Target width
 * @returns {string}
 */
function pad(str, width) {
  return String(str).padEnd(width);
}

// ============================================================================
// MAIN ENTRY POINT
// ============================================================================

async function main() {
  const apiKey = loadApiKey();
  console.log("API key loaded.\n");

  // -- Phase 1: Download all PDFs --
  console.log("=== Phase 1: Downloading PDFs ===");
  fs.mkdirSync(INPUT_DIR, { recursive: true });

  const downloadPromises = ARXIV_IDS.map((id, index) =>
    sleep(index * DOWNLOAD_STAGGER_MS).then(() => downloadPdf(id))
  );
  const downloads = await Promise.all(downloadPromises);

  const invalidPdfs = downloads.filter((d) => !d.valid);
  if (invalidPdfs.length > 0) {
    console.warn(
      `\nWARNING: ${invalidPdfs.length} file(s) did not have valid PDF magic bytes:`
    );
    invalidPdfs.forEach((d) => console.warn(`  - ${d.arxivId}`));
  }
  console.log(`\nAll ${downloads.length} PDFs downloaded.\n`);

  // Build a lookup for sizes
  const sizeMap = new Map(downloads.map((d) => [d.arxivId, d]));

  // -- Phase 2: Test OpenRouter pipeline (sequential) --
  console.log("=== Phase 2: Testing OpenRouter PDF URL pipeline ===");
  const results = [];
  for (let i = 0; i < ARXIV_IDS.length; i++) {
    const id = ARXIV_IDS[i];
    const result = await testOpenRouterPdf(id, apiKey);
    results.push(result);
    if (i < ARXIV_IDS.length - 1) {
      await sleep(REQUEST_DELAY_MS);
    }
  }
  console.log();

  // -- Phase 3: Print results --
  console.log("=== Phase 3: Results ===\n");

  // Merge download info with test results, sort by size ascending
  const merged = results.map((r) => ({
    ...r,
    sizeKB: sizeMap.get(r.arxivId)?.sizeKB ?? 0,
    sizeBytes: sizeMap.get(r.arxivId)?.sizeBytes ?? 0,
  }));
  merged.sort((a, b) => a.sizeKB - b.sizeKB);

  // Print table
  console.log(
    `${pad("arxiv_id", 16)}${pad("Size (KB)", 12)}${pad("Status", 9)}${pad("Time", 9)}Error`
  );
  console.log("-".repeat(80));
  for (const row of merged) {
    const time = `${row.timeSeconds.toFixed(1)}s`;
    const error = row.error || "";
    console.log(
      `${pad(row.arxivId, 16)}${pad(row.sizeKB, 12)}${pad(row.status, 9)}${pad(time, 9)}${error}`
    );
  }
  console.log();

  // Summary
  const okResults = merged.filter((r) => r.status === "OK");
  const failResults = merged.filter((r) => r.status === "FAIL");
  const largestOk =
    okResults.length > 0 ? Math.max(...okResults.map((r) => r.sizeKB)) : null;
  const smallestFail =
    failResults.length > 0
      ? Math.min(...failResults.map((r) => r.sizeKB))
      : null;

  console.log(`OK:   ${okResults.length} / ${merged.length}`);
  console.log(`FAIL: ${failResults.length} / ${merged.length}`);
  if (largestOk !== null) console.log(`Largest OK size:    ${largestOk} KB`);
  if (smallestFail !== null)
    console.log(`Smallest FAIL size: ${smallestFail} KB`);

  // Save JSON output
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  const outputPath = path.join(OUTPUT_DIR, "bulk-test-results.json");
  fs.writeFileSync(outputPath, JSON.stringify(merged, null, 2));
  console.log(`\nResults saved to ${outputPath}`);
}

main().catch((err) => {
  console.error("Fatal error:", err.message);
  process.exit(1);
});
