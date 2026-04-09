"""
Compute data-driven trend metrics for research themes.

Reads theme_assignments.json (from step 02) and derives velocity, status, and
weekly sparklines for each theme. Pure data analysis, no LLM calls.

Responsibilities:
- Read output/theme_assignments.json
- Compute weekly paper counts, velocity, and status per theme
- Rank and sort themes by status and velocity
- Write output/research_frontiers.json
- Print a formatted summary table to stdout
"""

import json
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = Path(__file__).parent
INPUT_PATH = SCRIPT_DIR / "output" / "theme_assignments.json"
OUTPUT_PATH = SCRIPT_DIR / "output" / "research_frontiers.json"

# Number of recent weeks to consider a theme "emerging"
EMERGING_WINDOW_WEEKS = 2

# Velocity thresholds for status classification
ACCELERATING_THRESHOLD = 50    # velocity > +50%
DECELERATING_THRESHOLD = -30   # velocity < -30%

# Max top papers to include per theme
TOP_PAPERS_LIMIT = 3

# Status sort priority (lower = first)
STATUS_SORT_ORDER = {
    "emerging": 0,
    "accelerating": 1,
    "stable": 2,
    "decelerating": 3,
    "dormant": 4,
}


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def main():
    raw = INPUT_PATH.read_text()
    data = json.loads(raw)

    # Step 02 output format:
    # {
    #   "themes": {name: {description, first_seen_week}},
    #   "weekly_assignments": {week: [{arxiv_id, title, themes}]},
    #   ...
    # }
    themes_registry = data["themes"]  # {name: {description, first_seen_week}}
    weekly_assignments = data["weekly_assignments"]  # {week: [{arxiv_id, title, themes}]}
    weeks_sorted = sorted(weekly_assignments.keys())

    if not weeks_sorted:
        raise ValueError("No weeks found in theme_assignments.json")

    # Build per-theme paper lists from weekly_assignments
    theme_papers = build_theme_papers(weekly_assignments)

    frontiers = []
    for theme_name, info in themes_registry.items():
        papers_by_week = theme_papers.get(theme_name, {})
        frontier = build_frontier(theme_name, info, papers_by_week, weeks_sorted)
        frontiers.append(frontier)

    frontiers.sort(key=sort_key)

    summary = build_summary(frontiers)

    result = {
        "frontiers": frontiers,
        "summary": summary,
        "weeks_analyzed": weeks_sorted,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2))

    print_summary_table(frontiers, weeks_sorted, summary)
    print(f"\nSaved to {OUTPUT_PATH}")


# ============================================================================
# MAIN LOGIC
# ============================================================================

def build_theme_papers(weekly_assignments):
    """
    Invert the weekly_assignments structure into {theme_name: {week: [arxiv_ids]}}.

    Args:
        weekly_assignments: {week: [{arxiv_id, title, themes}]}

    Returns:
        {theme_name: {week: [arxiv_id, ...]}}
    """
    theme_papers = {}
    for week, assignments in weekly_assignments.items():
        for assignment in assignments:
            arxiv_id = assignment.get("arxiv_id", "")
            for theme_name in assignment.get("themes", []):
                if theme_name not in theme_papers:
                    theme_papers[theme_name] = {}
                theme_papers[theme_name].setdefault(week, []).append(arxiv_id)
    return theme_papers


def build_frontier(theme_name, theme_info, papers_by_week, weeks_sorted):
    """
    Build a single frontier entry for a theme.

    Args:
        theme_name: the theme name string
        theme_info: {description, first_seen_week} from theme registry
        papers_by_week: {week: [arxiv_ids]} for this theme
        weeks_sorted: all weeks in ascending order

    Returns:
        dict matching the frontier output schema
    """
    weekly_counts = [len(papers_by_week.get(w, [])) for w in weeks_sorted]
    total_papers = sum(weekly_counts)

    first_seen = theme_info.get("first_seen_week") or find_first_seen(weekly_counts, weeks_sorted)
    velocity = compute_velocity(weekly_counts)
    status = determine_status(velocity, weekly_counts, weeks_sorted, first_seen)

    # Top papers from the most recent week
    most_recent_week = weeks_sorted[-1]
    recent_ids = papers_by_week.get(most_recent_week, [])
    top_papers = recent_ids[:TOP_PAPERS_LIMIT]

    return {
        "theme": theme_name,
        "description": theme_info.get("description", ""),
        "status": status,
        "total_papers": total_papers,
        "weekly_counts": weekly_counts,
        "velocity_pct": velocity,
        "first_seen": first_seen,
        "top_papers": top_papers,
    }


def build_summary(frontiers):
    """
    Build the summary dict counting themes per status.

    Args:
        frontiers: list of frontier dicts

    Returns:
        dict with total_themes and count per status
    """
    counts = {s: 0 for s in STATUS_SORT_ORDER}
    for f in frontiers:
        counts[f["status"]] += 1

    return {
        "total_themes": len(frontiers),
        **counts,
    }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def find_first_seen(weekly_counts, weeks_sorted):
    """
    Return the week_start string of the first week with papers.

    Args:
        weekly_counts: list of ints, one per week
        weeks_sorted: list of week_start strings

    Returns:
        week_start string or None if no papers at all
    """
    for count, week in zip(weekly_counts, weeks_sorted):
        if count > 0:
            return week
    return None


def compute_velocity(weekly_counts):
    """
    Compute velocity as percentage change: most recent week vs average of previous weeks.

    Args:
        weekly_counts: list of ints, one per week (ascending order)

    Returns:
        float percentage change, or the string "new" if previous average was 0
        but the most recent week has papers
    """
    if len(weekly_counts) < 2:
        return 0.0

    current = weekly_counts[-1]
    previous = weekly_counts[:-1]
    avg_previous = sum(previous) / len(previous)

    if avg_previous == 0:
        if current > 0:
            return "new"
        return 0.0

    return round(((current - avg_previous) / avg_previous) * 100, 1)


def determine_status(velocity, weekly_counts, weeks_sorted, first_seen):
    """
    Derive theme status from velocity and recency data.

    Args:
        velocity: float or "new"
        weekly_counts: list of ints per week
        weeks_sorted: list of week_start strings
        first_seen: week_start string of first appearance

    Returns:
        one of: "emerging", "accelerating", "stable", "decelerating", "dormant"
    """
    current = weekly_counts[-1] if weekly_counts else 0

    # Dormant: no papers in most recent week
    if current == 0:
        return "dormant"

    # Emerging: first appeared in the last N weeks and still active
    if first_seen is not None:
        emerging_cutoff_weeks = weeks_sorted[-EMERGING_WINDOW_WEEKS:]
        if first_seen in emerging_cutoff_weeks:
            return "emerging"

    # Velocity-based classification
    if velocity == "new":
        return "emerging"
    if velocity > ACCELERATING_THRESHOLD:
        return "accelerating"
    if velocity < DECELERATING_THRESHOLD:
        return "decelerating"

    return "stable"


def sort_key(frontier):
    """
    Sort key: status priority first, then velocity descending (for accelerating).

    Args:
        frontier: a frontier dict

    Returns:
        tuple for sorting
    """
    status_order = STATUS_SORT_ORDER.get(frontier["status"], 99)
    # Negate velocity for descending sort; handle "new" as very high
    vel = frontier["velocity_pct"]
    vel_sort = -(999999 if vel == "new" else vel)
    return (status_order, vel_sort)


def print_summary_table(frontiers, weeks_sorted, summary):
    """
    Print a formatted summary table to stdout.

    Args:
        frontiers: sorted list of frontier dicts
        weeks_sorted: list of week_start strings
        summary: summary dict with counts per status
    """
    # Header
    week_headers = [w[5:] for w in weeks_sorted]  # trim year, e.g. "03-12"
    week_col_width = max(len(h) for h in week_headers) + 1

    print("=" * 90)
    print("RESEARCH FRONTIERS SUMMARY")
    print("=" * 90)
    print()

    header = f"{'Theme':<40} {'Status':<15} {'Vel%':>6}  "
    header += "  ".join(f"{h:>{week_col_width}}" for h in week_headers)
    header += f"  {'Total':>5}"
    print(header)
    print("-" * len(header))

    for f in frontiers:
        vel_str = "new" if f["velocity_pct"] == "new" else f"{f['velocity_pct']:+.1f}"
        name = f["theme"][:38]
        counts_str = "  ".join(
            f"{c:>{week_col_width}}" for c in f["weekly_counts"]
        )
        print(
            f"{name:<40} {f['status']:<15} {vel_str:>6}  "
            f"{counts_str}  {f['total_papers']:>5}"
        )

    print()
    print(f"Total themes: {summary['total_themes']}")
    for status in STATUS_SORT_ORDER:
        count = summary.get(status, 0)
        if count > 0:
            print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
