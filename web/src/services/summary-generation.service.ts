/**
 * Server-side service for on-demand summary generation.
 *
 * Orchestrates generating a 5-minute summary for a paper that was processed
 * without one (status=partially_completed). Uses Gemini 3 Flash via OpenRouter.
 *
 * Responsibilities:
 * - Check if summary already exists (early return)
 * - Download paper content from Supabase Storage
 * - Generate summary via LLM
 * - Atomically save summary (race-safe via set_paper_summary_if_null RPC)
 */

import { createClient } from '@/lib/supabase/server';
import { downloadPaperMarkdown } from '@/lib/supabase/storage';
import { chatCompletion } from '@/lib/openrouter';

// ============================================================================
// CONSTANTS
// ============================================================================

const FLASH_MODEL = 'google/gemini-3-flash-preview';

const SUMMARY_PROMPT = `You are a technical writer creating a simple, easy to read 5-minute summary of a research paper. Your goal is to make complex research accessible to a general audience while preserving the core insights and contributions. You do this in a simple language, getting difficult concepts across in a very simple way.

## Target Audience
- General readers with basic technical literacy
- People who want to understand the paper's value without reading the full text
- Professionals from related fields seeking quick insights

## Content Requirements

**Structure your summary with these sections:**

1. **What This Paper Is About** (1-2 paragraphs)
   - Main research question or problem being solved. State this question or problem explicitely.
   - Why this problem matters

2. **Key Approach** (1-2 paragraphs)
   - How the researchers tackled the problem
   - Main methodology or technique used
   - What makes their approach novel or different

3. **Main Findings** (1-2 paragraphs)
   - Core results and discoveries
   - Key data points or performance metrics
   - Most important conclusions

4. **Why This Matters** (1 paragraph)
   - Real-world implications
   - Impact on the field or industry
   - Future applications or research directions

Use level 2 formatting (##) for each section inside the summary. Do not add a level 1 heading.

## Writing Guidelines

- **Length**: Aim for 500-700 words total (truly readable in 5 minutes)
- **Language**: Use clear, straightforward language. Explain technical terms when necessary
- **Tone**: Engaging but professional, avoid academic jargon. Use simple terms in favour of difficult names. Avoid buzzwords.
- Avoid overusing adjectives that are purely meant to inflate the paper (eg. instead of "cleverly uses", say "uses". Instead of "much-needed tool", say "new tool")
- **Focus**: Emphasize practical significance and broader impact
- **Structure**: Use clear headings and short paragraphs for easy scanning
- Do not use quotes around standalone words (eg. "expert"), quotes should be used for actual quotes only.
- **Avoid long sentences.**

## Formatting

- Use markdown headings for each section
- Use bullet points or numbered lists where helpful for clarity
- Bold key terms or important findings
- Keep paragraphs short (3-4 sentences max)

Return only the summary text. Do not include any other text, meta-commentary, or explanations about the summary itself.`;

// ============================================================================
// INTERFACES
// ============================================================================

export interface GenerateSummaryResult {
  /** The generated or existing summary text */
  summary: string;
  /** Whether the summary already existed (another request beat us) */
  alreadyExisted: boolean;
}

// ============================================================================
// MAIN ENTRYPOINT
// ============================================================================

/**
 * Generate a 5-minute summary for a paper on demand.
 * Race-safe: uses atomic conditional write so concurrent requests don't corrupt data.
 *
 * @param paperUuid - UUID of the paper to summarize
 * @returns Generated summary text and whether it already existed
 */
export async function generateSummaryForPaper(paperUuid: string): Promise<GenerateSummaryResult> {
  const supabase = await createClient();

  // Step 1: Check if summary already exists
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: existingPaper, error: fetchError } = await (supabase
    .from('papers') as any)
    .select('summaries, status')
    .eq('paper_uuid', paperUuid)
    .single() as { data: { summaries: Record<string, string> | null; status: string } | null; error: { message: string } | null };

  if (fetchError || !existingPaper) throw new Error(`Paper not found: ${fetchError?.message}`);

  const existingSummary = existingPaper.summaries?.five_minute_summary;
  if (existingSummary) {
    return { summary: existingSummary, alreadyExisted: true };
  }

  // Step 2: Download content.md from Supabase Storage (uses service role key)
  const contentMarkdown = await downloadPaperMarkdown(paperUuid);

  // Step 3: Generate summary via Gemini 3 Flash
  const response = await chatCompletion(
    [
      { role: 'system', content: SUMMARY_PROMPT },
      { role: 'user', content: contentMarkdown },
    ],
    FLASH_MODEL
  );

  const generatedSummary = response.text;

  // Step 4: Atomically save summary (race-safe)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: rpcResult, error: rpcError } = await (supabase as any).rpc('set_paper_summary_if_null', {
    p_paper_uuid: paperUuid,
    p_summary: generatedSummary,
  }) as { data: { was_set: boolean }[] | null; error: { message: string } | null };

  if (rpcError) throw new Error(`Failed to save summary: ${rpcError.message}`);

  // Check if we won the race
  const wasSet = rpcResult?.[0]?.was_set ?? false;

  if (!wasSet) {
    // Another request already wrote a summary - fetch and return it
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const { data: updatedPaper } = await (supabase
      .from('papers') as any)
      .select('summaries')
      .eq('paper_uuid', paperUuid)
      .single() as { data: { summaries: Record<string, string> | null } | null; error: unknown };

    const existingSummaryText = updatedPaper?.summaries?.five_minute_summary;
    return { summary: existingSummaryText ?? generatedSummary, alreadyExisted: true };
  }

  return { summary: generatedSummary, alreadyExisted: false };
}
