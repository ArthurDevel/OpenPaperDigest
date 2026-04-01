# OpenRouter PDF Debug -- Investigation Writeup

## Goal

Investigate why OpenRouter returns "Provider returned error" (code 400) for certain papers during summary generation.

## Root Cause

OpenRouter fails to fetch large PDFs by URL. When a PDF is sent as a URL in the `file_data` field, OpenRouter's servers must download it. For large PDFs (~22 MB+), this fails with "Provider returned error" (code 400), returned inside an HTTP 200 response body.

## Evidence

### Test 1: Bulk URL test (`test-bulk-papers.ts`)

Tested 10 arxiv papers via URL. 2 out of 10 failed:

| Paper       | Result |
|-------------|--------|
| 2601.02350  | FAIL   |
| 2603.09465  | FAIL   |
| All others  | PASS   |

### Test 2: Base64 fallback (`test-base64-fallback.ts`)

Both failing papers work perfectly when downloaded locally and sent as base64 data URIs:

- **2601.02350** (22.02 MB) -- OK in 16.8s
- **2603.09465** (22.68 MB) -- OK in 10.7s

### Test 3: PDF size correlation (`test-pdf-sizes.ts`)

Clear size correlation:

- **Failed PDFs:** 22.02 MB and 22.68 MB
- **Passed PDFs:** 547 KB to 5.67 MB
- **Gap:** no PDFs tested between 5.67 MB and 22 MB
- No redirect issues -- all URLs return HTTP 200 with `application/pdf`

### Test 4: Initial test (`test-openrouter-pdf.ts`)

Confirmed the original failing paper works via base64 but fails via URL.

## Bug in Current Code

In `summary-generation.service.ts`, when the URL-based call fails, the fallback downloads `content.md` from Supabase Storage. But v2 pipeline papers don't have `content.md`, so `downloadPaperMarkdown()` returns an empty string. This empty string is sent to OpenRouter, which returns an empty response, causing the "OpenRouter returned empty response" error.

## Recommended Fix

When the URL-based PDF call fails, download the PDF ourselves and re-send it as a base64 data URI, instead of falling back to `content.md`. This works for all tested papers regardless of size.

## How to Run

```bash
cd testscripts/2026.04.01-openrouter-pdf-debug
cp .env.example .env  # fill in OPENROUTER_API_KEY
npm install
npx tsx test-openrouter-pdf.ts       # original 3-test comparison
npx tsx test-bulk-papers.ts          # bulk URL test (10 papers)
npx tsx test-base64-fallback.ts      # base64 fallback for failures
npx tsx test-pdf-sizes.ts            # PDF size analysis
```
