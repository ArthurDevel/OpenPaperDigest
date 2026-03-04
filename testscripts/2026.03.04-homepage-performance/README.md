# Homepage Performance Tests

Tests to measure API bottlenecks during homepage load.

## What the homepage does on load

1. `GET /api/papers/minimal?page=1&limit=20` - fetches the paper list
2. `GET /api/papers/{uuid}/summary` x20 - eagerly pre-fetches summaries for **all** cards before user interaction

## Scripts

### test_api_response_times.py

Measures response times for the full homepage data loading flow.

```bash
python test_api_response_times.py http://localhost:3000
python test_api_response_times.py https://your-deployed-url.com
```

### test_summary_payload_sizes.py

Measures payload sizes and breaks down which fields contribute most to the response size.

```bash
python test_summary_payload_sizes.py http://localhost:3000
python test_summary_payload_sizes.py https://your-deployed-url.com
```

## Known issues identified

1. **20 eager summary fetches** - summaries are pre-fetched for all cards even though users only expand 1-2
2. **~2MB DB read per summary** - server fetches the full `processed_content` column from Supabase just to extract `five_minute_summary`
3. **No SSR** - homepage is fully client-rendered (`"use client"`), so the browser gets an empty shell
4. **Heavy markdown pipeline x20** - `react-markdown + remarkGfm + remarkMath + rehypeKatex` is instantiated per card
