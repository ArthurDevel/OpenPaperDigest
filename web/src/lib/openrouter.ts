/**
 * Thin OpenRouter client for calling LLMs from Next.js server-side routes.
 *
 * Responsibilities:
 * - Send chat completion requests to OpenRouter API
 * - Support multimodal content (text, images, files/PDFs)
 * - Handle retries with exponential backoff
 * - Return structured response with token usage and cost
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions';
const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;
const PDF_MAX_SIZE_BYTES = 50 * 1024 * 1024;
const PDF_DOWNLOAD_TIMEOUT_MS = 60_000;

// ============================================================================
// INTERFACES
// ============================================================================

/** A text content part for multimodal messages */
export interface TextPart {
  type: 'text';
  text: string;
}

/** An image URL content part for multimodal messages */
export interface ImageUrlPart {
  type: 'image_url';
  image_url: { url: string };
}

/** A file content part (e.g. PDF via URL or base64 data URI) */
export interface FilePart {
  type: 'file';
  file: { filename: string; file_data: string };
}

/** Union of all supported content part types */
export type ContentPart = TextPart | ImageUrlPart | FilePart;

export interface OpenRouterMessage {
  role: 'system' | 'user' | 'assistant';
  content: string | ContentPart[];
}

/** OpenRouter plugin configuration (e.g. PDF engine selection) */
export interface Plugin {
  id: string;
  pdf?: { engine: string };
}

export interface OpenRouterResponse {
  /** Generated text content */
  text: string;
  /** Number of prompt tokens used */
  promptTokens: number;
  /** Number of completion tokens generated */
  completionTokens: number;
  /** Estimated cost in USD */
  cost: number;
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

/**
 * Send a chat completion request to OpenRouter.
 * Includes retry logic with exponential backoff (3 attempts).
 * @param messages - Array of chat messages (supports text and multimodal content)
 * @param model - OpenRouter model identifier
 * @param plugins - Optional plugins (e.g. for PDF native engine)
 * @returns Response with generated text and usage metrics
 */
export async function chatCompletion(
  messages: OpenRouterMessage[],
  model: string,
  plugins?: Plugin[]
): Promise<OpenRouterResponse> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    throw new Error('OPENROUTER_API_KEY environment variable is not set');
  }

  // Build request payload, conditionally including plugins
  const payload: Record<string, unknown> = { model, messages };
  if (plugins) {
    payload.plugins = plugins;
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    let retryable = true;
    try {
      const response = await fetch(OPENROUTER_API_URL, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        if (response.status >= 400 && response.status < 500) retryable = false;
        throw new Error(`OpenRouter API error ${response.status}: ${errorBody}`);
      }

      const data = await response.json();

      // OpenRouter sometimes returns errors with HTTP 200
      if (data.error) {
        const errMsg = data.error.message || JSON.stringify(data.error);
        const code = data.error.code ?? 0;
        console.error(`[OpenRouter] API error (code ${code}): ${errMsg}`);
        if (code >= 400 && code < 500) retryable = false;
        throw new Error(`OpenRouter API error: ${errMsg}`);
      }

      const choice = data.choices?.[0];

      if (!choice?.message?.content) {
        console.error('[OpenRouter] Empty content. Full response:', JSON.stringify(data, null, 2));
        throw new Error('OpenRouter returned empty response');
      }

      return {
        text: choice.message.content,
        promptTokens: data.usage?.prompt_tokens ?? 0,
        completionTokens: data.usage?.completion_tokens ?? 0,
        cost: data.usage?.total_cost ?? 0,
      };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      if (!retryable) break;

      if (attempt < MAX_RETRIES - 1) {
        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError ?? new Error('OpenRouter request failed after retries');
}

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

/**
 * Download a PDF from a URL and return it as a base64 data URI string.
 * Validates Content-Type is application/pdf, enforces 50MB max size,
 * and uses a 60s timeout via AbortController.
 *
 * @param url - URL of the PDF to download
 * @returns Base64 data URI string (data:application/pdf;base64,...)
 */
export async function downloadPdfAsBase64(url: string): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PDF_DOWNLOAD_TIMEOUT_MS);

  try {
    const response = await fetch(url, { signal: controller.signal });

    if (!response.ok) {
      throw new Error(`PDF download failed with status ${response.status}`);
    }

    // Validate content type
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/pdf')) {
      throw new Error(`Expected application/pdf but got ${contentType}`);
    }

    // Download body and enforce size limit
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > PDF_MAX_SIZE_BYTES) {
      throw new Error(`PDF exceeds max size: ${buffer.byteLength} bytes (limit ${PDF_MAX_SIZE_BYTES})`);
    }

    // Convert to base64 data URI
    const base64 = Buffer.from(buffer).toString('base64');
    return `data:application/pdf;base64,${base64}`;
  } finally {
    clearTimeout(timeoutId);
  }
}
