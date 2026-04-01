/**
 * Test script: Base64 PDF fallback for OpenRouter + Gemini
 *
 * Tests whether sending PDFs as base64 data URIs works for papers that fail via URL.
 * - Downloads PDFs from arxiv
 * - Base64 encodes them
 * - Sends to OpenRouter with file_data field
 * - Logs success/failure, response preview, and timing
 */

import "dotenv/config";
import * as fs from "fs";
import * as path from "path";
import * as https from "https";

// ============================================================================
// CONSTANTS
// ============================================================================

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY;
if (!OPENROUTER_API_KEY) {
  throw new Error("OPENROUTER_API_KEY not set in .env");
}

const ARXIV_IDS = ["2601.02350", "2603.09465"];
const MODEL = "google/gemini-3-flash-preview";
const INPUT_DIR = path.join(__dirname, "input");
const OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";

interface TestResult {
  arxivId: string;
  fileSizeBytes: number;
  success: boolean;
  responsePreview: string;
  timeTakenMs: number;
  error?: string;
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

async function main(): Promise<void> {
  fs.mkdirSync(INPUT_DIR, { recursive: true });

  const results: TestResult[] = [];

  for (const arxivId of ARXIV_IDS) {
    console.log(`\n--- Testing arxiv ID: ${arxivId} ---`);
    const result = await testPaper(arxivId);
    results.push(result);
  }

  printSummaryTable(results);
}

// ============================================================================
// MAIN LOGIC
// ============================================================================

/**
 * Downloads, encodes, and sends a single paper to OpenRouter.
 * @param arxivId - The arxiv paper ID
 * @returns TestResult with timing and response info
 */
async function testPaper(arxivId: string): Promise<TestResult> {
  const pdfPath = path.join(INPUT_DIR, `${arxivId.replace("/", "_")}.pdf`);

  // Step 1: Download
  console.log(`Downloading https://arxiv.org/pdf/${arxivId} ...`);
  await downloadFile(`https://arxiv.org/pdf/${arxivId}`, pdfPath);

  // Step 2: Check file size
  const stats = fs.statSync(pdfPath);
  const fileSizeBytes = stats.size;
  console.log(`File size: ${(fileSizeBytes / 1024 / 1024).toFixed(2)} MB (${fileSizeBytes} bytes)`);

  // Step 3: Base64 encode
  const pdfBuffer = fs.readFileSync(pdfPath);
  const base64Data = pdfBuffer.toString("base64");
  const dataUri = `data:application/pdf;base64,${base64Data}`;
  console.log(`Base64 length: ${base64Data.length} chars`);

  // Step 4: Send to OpenRouter
  const start = Date.now();
  try {
    const responseText = await sendToOpenRouter(dataUri, arxivId);
    const timeTakenMs = Date.now() - start;
    console.log(`SUCCESS (${timeTakenMs}ms): ${responseText.substring(0, 200)}`);

    return {
      arxivId,
      fileSizeBytes,
      success: true,
      responsePreview: responseText.substring(0, 200),
      timeTakenMs,
    };
  } catch (err: unknown) {
    const timeTakenMs = Date.now() - start;
    const errorMsg = err instanceof Error ? err.message : String(err);
    console.log(`FAILED (${timeTakenMs}ms): ${errorMsg}`);

    return {
      arxivId,
      fileSizeBytes,
      success: false,
      responsePreview: "",
      timeTakenMs,
      error: errorMsg,
    };
  }
}

/**
 * Sends a base64-encoded PDF to OpenRouter and returns the assistant message.
 * @param dataUri - The full data URI string (data:application/pdf;base64,...)
 * @param arxivId - For logging context
 * @returns The assistant's response text
 */
async function sendToOpenRouter(dataUri: string, arxivId: string): Promise<string> {
  const payload = {
    model: MODEL,
    messages: [
      { role: "system", content: "Summarize this paper in one sentence." },
      {
        role: "user",
        content: [
          { type: "text", text: "Please summarize this research paper." },
          {
            type: "file",
            file: {
              filename: `${arxivId}.pdf`,
              file_data: dataUri,
            },
          },
        ],
      },
    ],
    plugins: [{ id: "file-parser", pdf: { engine: "native" } }],
  };

  const response = await fetch(OPENROUTER_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json();

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${JSON.stringify(body)}`);
  }

  const content = body?.choices?.[0]?.message?.content;
  if (!content) {
    throw new Error(`No content in response: ${JSON.stringify(body).substring(0, 500)}`);
  }

  return content;
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Downloads a file from a URL, following redirects.
 * @param url - The URL to download from
 * @param destPath - Local file path to save to
 */
function downloadFile(url: string, destPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = https.get(url, (response) => {
      // Follow redirects (arxiv often redirects)
      if (response.statusCode === 301 || response.statusCode === 302) {
        const redirectUrl = response.headers.location;
        if (!redirectUrl) {
          reject(new Error("Redirect without location header"));
          return;
        }
        downloadFile(redirectUrl, destPath).then(resolve).catch(reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`Download failed with status ${response.statusCode}`));
        return;
      }

      const file = fs.createWriteStream(destPath);
      response.pipe(file);
      file.on("finish", () => {
        file.close();
        resolve();
      });
      file.on("error", reject);
    });

    request.on("error", reject);
  });
}

/**
 * Prints a formatted summary table of all test results.
 * @param results - Array of test results
 */
function printSummaryTable(results: TestResult[]): void {
  console.log("\n\n========================================");
  console.log("SUMMARY TABLE");
  console.log("========================================");
  console.log(
    "ArxivID".padEnd(16) +
      "Size(MB)".padEnd(10) +
      "Status".padEnd(10) +
      "Time(s)".padEnd(10) +
      "Response/Error"
  );
  console.log("-".repeat(80));

  for (const r of results) {
    const sizeMB = (r.fileSizeBytes / 1024 / 1024).toFixed(2);
    const status = r.success ? "OK" : "FAIL";
    const timeSec = (r.timeTakenMs / 1000).toFixed(1);
    const preview = r.success ? r.responsePreview.substring(0, 40) : (r.error ?? "").substring(0, 40);

    console.log(
      r.arxivId.padEnd(16) +
        sizeMB.padEnd(10) +
        status.padEnd(10) +
        timeSec.padEnd(10) +
        preview
    );
  }

  console.log("========================================\n");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
