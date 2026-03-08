/**
 * Thin OpenRouter client for calling LLMs from Next.js server-side routes.
 *
 * Responsibilities:
 * - Send chat completion requests to OpenRouter API
 * - Handle retries with exponential backoff
 * - Return structured response with token usage and cost
 */

// ============================================================================
// CONSTANTS
// ============================================================================

const OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/chat/completions';
const MAX_RETRIES = 3;
const BASE_DELAY_MS = 1000;

// ============================================================================
// INTERFACES
// ============================================================================

export interface OpenRouterMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
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
 * @param messages - Array of chat messages
 * @param model - OpenRouter model identifier
 * @returns Response with generated text and usage metrics
 */
export async function chatCompletion(
  messages: OpenRouterMessage[],
  model: string
): Promise<OpenRouterResponse> {
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    throw new Error('OPENROUTER_API_KEY environment variable is not set');
  }

  let lastError: Error | null = null;

  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const response = await fetch(OPENROUTER_API_URL, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
          'HTTP-Referer': process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000',
        },
        body: JSON.stringify({ model, messages }),
      });

      if (!response.ok) {
        const errorBody = await response.text();
        throw new Error(`OpenRouter API error ${response.status}: ${errorBody}`);
      }

      const data = await response.json();
      const choice = data.choices?.[0];

      if (!choice?.message?.content) {
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

      if (attempt < MAX_RETRIES - 1) {
        const delay = BASE_DELAY_MS * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }

  throw lastError ?? new Error('OpenRouter request failed after retries');
}
