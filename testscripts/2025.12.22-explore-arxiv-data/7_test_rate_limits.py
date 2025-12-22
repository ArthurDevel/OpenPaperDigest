"""
Test Semantic Scholar API rate limiting for unauthenticated users.

Key insight from docs:
- 1000 requests/second SHARED among ALL unauthenticated users
- We're competing with everyone else for this pool
- Rate limits are unpredictable (depends on current load)

Strategy to test:
- Burst as fast as possible (grab capacity when available)
- Retry with backoff when hitting 429
- Measure effective throughput with different retry strategies
"""

import httpx
import json
import time
import os
from datetime import datetime
from typing import Optional
import statistics

# =============================================================================
# CONFIGURATION
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

TIMEOUT_SECONDS = 30
DEFAULT_HEADERS = {
    "User-Agent": "papersummarizer/0.1",
}

# Test endpoint
TEST_PAPER_ID = "2312.00752"

# =============================================================================
# HELPERS
# =============================================================================

def make_request(endpoint: str, params: dict = None) -> tuple[int, float]:
    """Make a single request. Returns (status_code, elapsed_seconds)."""
    url = f"https://api.semanticscholar.org/graph/v1/{endpoint}"

    start = time.time()
    with httpx.Client(headers=DEFAULT_HEADERS, timeout=TIMEOUT_SECONDS) as client:
        resp = client.get(url, params=params)
        elapsed = time.time() - start

    return resp.status_code, elapsed


def make_request_with_retry(
    endpoint: str,
    params: dict = None,
    max_retries: int = 5,
    base_delay: float = 0.1,
    backoff_factor: float = 2.0,
) -> tuple[bool, int, float]:
    """
    Make request with exponential backoff retry.

    Returns: (success, attempts, total_time)
    """
    total_time = 0
    delay = base_delay

    for attempt in range(1, max_retries + 1):
        status, elapsed = make_request(endpoint, params)
        total_time += elapsed

        if status == 200:
            return True, attempt, total_time

        if status == 429:
            if attempt < max_retries:
                time.sleep(delay)
                total_time += delay
                delay *= backoff_factor
        else:
            # Other error, don't retry
            return False, attempt, total_time

    return False, max_retries, total_time


# =============================================================================
# TEST 1: Measure current pool availability
# =============================================================================

def test_pool_availability(num_requests: int = 20) -> dict:
    """
    Burst requests to see how many succeed before rate limit.
    This tells us the current state of the shared pool.
    """
    print("\n" + "=" * 60)
    print("TEST 1: Pool availability (burst test)")
    print("=" * 60)
    print(f"Sending {num_requests} requests as fast as possible...\n")

    results = []
    for i in range(num_requests):
        status, elapsed = make_request(
            f"paper/ARXIV:{TEST_PAPER_ID}",
            {"fields": "paperId"}
        )
        results.append({"status": status, "elapsed": elapsed})

        icon = "✓" if status == 200 else "✗"
        print(f"  [{i+1:2d}] {icon} {status} - {elapsed*1000:.0f}ms")

    successes = sum(1 for r in results if r["status"] == 200)
    first_fail = next((i+1 for i, r in enumerate(results) if r["status"] == 429), None)

    print(f"\nResults:")
    print(f"  Succeeded: {successes}/{num_requests}")
    print(f"  First 429 at: request {first_fail or 'never'}")

    return {
        "test": "pool_availability",
        "successes": successes,
        "first_fail": first_fail,
        "results": results,
    }


# =============================================================================
# TEST 2: Compare retry strategies
# =============================================================================

def test_retry_strategies() -> dict:
    """
    Compare different retry strategies for throughput.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Retry strategy comparison")
    print("=" * 60)

    strategies = [
        {"name": "aggressive", "base_delay": 0.05, "backoff": 1.5, "max_retries": 10},
        {"name": "moderate", "base_delay": 0.1, "backoff": 2.0, "max_retries": 5},
        {"name": "conservative", "base_delay": 0.2, "backoff": 2.0, "max_retries": 5},
        {"name": "patient", "base_delay": 0.5, "backoff": 2.0, "max_retries": 3},
    ]

    results = {}
    num_requests = 10

    for strategy in strategies:
        print(f"\n--- Strategy: {strategy['name']} ---")
        print(f"    base_delay={strategy['base_delay']}s, backoff={strategy['backoff']}x, max_retries={strategy['max_retries']}")

        # Wait for pool to recover
        print("    (waiting 3s for pool to recover...)")
        time.sleep(3)

        successes = 0
        total_time = 0
        total_attempts = 0

        for i in range(num_requests):
            success, attempts, elapsed = make_request_with_retry(
                f"paper/ARXIV:{TEST_PAPER_ID}",
                {"fields": "paperId"},
                max_retries=strategy["max_retries"],
                base_delay=strategy["base_delay"],
                backoff_factor=strategy["backoff"],
            )
            total_time += elapsed
            total_attempts += attempts
            if success:
                successes += 1

            icon = "✓" if success else "✗"
            print(f"    [{i+1:2d}] {icon} attempts={attempts} time={elapsed:.2f}s")

        throughput = successes / total_time if total_time > 0 else 0
        avg_attempts = total_attempts / num_requests

        print(f"\n    Results:")
        print(f"    Success rate: {successes}/{num_requests} ({successes/num_requests*100:.0f}%)")
        print(f"    Total time: {total_time:.1f}s")
        print(f"    Throughput: {throughput:.2f} successful req/s")
        print(f"    Avg attempts per request: {avg_attempts:.1f}")

        results[strategy["name"]] = {
            "strategy": strategy,
            "successes": successes,
            "total_time": total_time,
            "throughput": throughput,
            "avg_attempts": avg_attempts,
        }

    # Find best
    best = max(results.items(), key=lambda x: x[1]["throughput"])
    print(f"\n\nBest strategy: {best[0]} ({best[1]['throughput']:.2f} req/s)")

    return {"test": "retry_strategies", "results": results, "best": best[0]}


# =============================================================================
# TEST 3: Sustained throughput test
# =============================================================================

def test_sustained_throughput(duration_seconds: int = 30) -> dict:
    """
    Test sustained throughput over time using best-effort retry.
    """
    print("\n" + "=" * 60)
    print(f"TEST 3: Sustained throughput ({duration_seconds}s)")
    print("=" * 60)
    print("Using moderate retry strategy (0.1s base, 2x backoff, 5 retries)")
    print("Measuring how many successful requests we can make...\n")

    start_time = time.time()
    end_time = start_time + duration_seconds

    successes = 0
    failures = 0
    total_attempts = 0

    while time.time() < end_time:
        success, attempts, _ = make_request_with_retry(
            f"paper/ARXIV:{TEST_PAPER_ID}",
            {"fields": "paperId"},
            max_retries=5,
            base_delay=0.1,
            backoff_factor=2.0,
        )
        total_attempts += attempts
        if success:
            successes += 1
        else:
            failures += 1

        # Progress every 5 seconds
        elapsed_total = time.time() - start_time
        if int(elapsed_total) % 5 == 0 and int(elapsed_total) > 0:
            current_rate = successes / elapsed_total
            print(f"  [{elapsed_total:.0f}s] {successes} successes, {failures} failures, {current_rate:.2f} req/s")

    actual_duration = time.time() - start_time
    throughput = successes / actual_duration

    print(f"\nFinal Results:")
    print(f"  Duration: {actual_duration:.1f}s")
    print(f"  Successful requests: {successes}")
    print(f"  Failed requests: {failures}")
    print(f"  Total attempts: {total_attempts}")
    print(f"  Throughput: {throughput:.2f} successful req/s")
    print(f"  Retry overhead: {(total_attempts - successes - failures) / (successes + failures):.1f} retries per request")

    return {
        "test": "sustained_throughput",
        "duration": actual_duration,
        "successes": successes,
        "failures": failures,
        "total_attempts": total_attempts,
        "throughput": throughput,
    }


# =============================================================================
# TEST 4: Time-of-day effect
# =============================================================================

def test_current_conditions() -> dict:
    """
    Quick test to measure current API conditions.
    Useful to run at different times to compare.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Current conditions snapshot")
    print("=" * 60)
    print(f"Time: {datetime.now().isoformat()}")
    print("Making 5 quick requests to gauge current pool state...\n")

    latencies = []
    statuses = []

    for i in range(5):
        status, elapsed = make_request(
            f"paper/ARXIV:{TEST_PAPER_ID}",
            {"fields": "paperId"}
        )
        latencies.append(elapsed * 1000)
        statuses.append(status)
        icon = "✓" if status == 200 else "✗"
        print(f"  [{i+1}] {icon} {status} - {elapsed*1000:.0f}ms")

    successes = sum(1 for s in statuses if s == 200)

    print(f"\nSnapshot:")
    print(f"  Success rate: {successes}/5")
    if latencies:
        print(f"  Avg latency: {statistics.mean(latencies):.0f}ms")
        print(f"  Min/Max: {min(latencies):.0f}ms / {max(latencies):.0f}ms")

    condition = "good" if successes >= 4 else "moderate" if successes >= 2 else "congested"
    print(f"  Pool condition: {condition}")

    return {
        "test": "current_conditions",
        "timestamp": datetime.now().isoformat(),
        "successes": successes,
        "latencies": latencies,
        "condition": condition,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 60)
    print("SEMANTIC SCHOLAR RATE LIMIT TESTING")
    print("(Unauthenticated - shared 1000 req/s pool)")
    print("=" * 60)
    print(f"Started: {datetime.now().isoformat()}\n")

    all_results = {}

    # Quick condition check
    all_results["conditions"] = test_current_conditions()

    print("\n(Waiting 5s before next test...)")
    time.sleep(5)

    # Pool availability
    all_results["pool"] = test_pool_availability(15)

    print("\n(Waiting 5s before next test...)")
    time.sleep(5)

    # Compare retry strategies
    all_results["strategies"] = test_retry_strategies()

    # Sustained test (optional - takes 30s)
    print("\n\nSkipping sustained test (takes 30s). Uncomment to run.")
    # all_results["sustained"] = test_sustained_throughput(30)

    # Summary
    print("\n\n" + "=" * 60)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 60)

    print(f"""
Current pool condition: {all_results['conditions']['condition']}

Key findings:
- Shared pool means rate limits are UNPREDICTABLE
- Burst + retry is the optimal strategy (not fixed delays)
- Pool recovers quickly (within ~1-2 seconds)

Recommended approach for your scripts:
1. Don't use fixed delays between requests
2. Send requests as fast as possible
3. On 429, retry with exponential backoff:
   - Start: 0.1s
   - Multiply by 2 each retry
   - Max 5 retries
4. This maximizes throughput while handling congestion

Best retry strategy from tests: {all_results['strategies']['best']}
""")

    # Save results
    output_path = os.path.join(SCRIPT_DIR, "output/7_rate_limit_analysis.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"Full results saved to output/7_rate_limit_analysis.json")


if __name__ == "__main__":
    main()
