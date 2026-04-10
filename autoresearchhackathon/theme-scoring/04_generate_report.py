"""
Generates a standalone HTML report from the theme-scoring optimization loop results.

Responsibilities:
- Reads loop_results.json produced by the optimization loop
- Generates an SVG score evolution chart (no external libraries)
- Produces a styled HTML report with iteration details, stats, and formula explanation
- Writes output to output/autoresearch_report.html
"""

import json
import os

# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "output", "loop_results.json")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output", "autoresearch_report.html")

CHART_WIDTH = 800
CHART_HEIGHT = 300
CHART_PADDING_LEFT = 60
CHART_PADDING_RIGHT = 30
CHART_PADDING_TOP = 20
CHART_PADDING_BOTTOM = 40


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    with open(INPUT_PATH, "r") as f:
        data = json.load(f)

    html = build_html(data)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    print(f"Report saved to {OUTPUT_PATH}")


# ============================================================================
# HTML GENERATION
# ============================================================================

def build_html(data):
    iterations = data["iterations"]
    baseline_score = data["baseline_score"]
    best_score = data["best_score"]
    total_cost = data["total_cost"]

    kept_count = sum(1 for it in iterations if it["kept"])
    total_count = len(iterations)
    improvement_pct = ((best_score - baseline_score) / baseline_score) * 100

    svg_chart = build_svg_chart(iterations, baseline_score)
    iterations_rows = build_iterations_rows(iterations)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Autoresearch: Theme Detection Optimization</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0f172a;
    color: #e2e8f0;
    font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    line-height: 1.6;
    padding: 2rem 1rem;
  }}
  .container {{ max-width: 1000px; margin: 0 auto; }}

  /* Title */
  h1 {{ font-size: 1.75rem; font-weight: 700; margin-bottom: 0.25rem; }}
  .subtitle {{ color: #94a3b8; font-size: 0.95rem; margin-bottom: 2rem; }}

  /* Chart */
  .chart-container {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    overflow-x: auto;
  }}
  .chart-container svg {{ display: block; margin: 0 auto; max-width: 100%; height: auto; }}

  /* Formula box */
  .formula-box {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    font-size: 0.85rem;
    line-height: 1.8;
    color: #94a3b8;
    white-space: pre-line;
  }}
  .formula-box .highlight {{ color: #e2e8f0; font-weight: 600; }}

  /* Stats row */
  .stats-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
  }}
  .stat-card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.25rem;
    text-align: center;
  }}
  .stat-card .label {{ color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.5rem; }}
  .stat-card .value {{ font-size: 1.5rem; font-weight: 700; }}
  .stat-card .detail {{ color: #94a3b8; font-size: 0.8rem; margin-top: 0.25rem; }}
  .green {{ color: #22c55e; }}
  .red {{ color: #ef4444; }}

  /* Table */
  .table-container {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    overflow-x: auto;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
  th {{
    text-align: left;
    padding: 0.75rem 1rem;
    color: #94a3b8;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 1px solid #334155;
  }}
  td {{
    padding: 0.65rem 1rem;
    border-bottom: 1px solid #334155;
    vertical-align: top;
  }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .badge-kept {{ background: rgba(34, 197, 94, 0.15); color: #22c55e; }}
  .badge-reverted {{ background: rgba(239, 68, 68, 0.15); color: #ef4444; }}
  .mutation-text {{ color: #94a3b8; font-size: 0.8rem; max-width: 250px; }}

  /* How it works */
  .how-it-works {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
  }}
  .how-title {{
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 1rem;
  }}
  .how-steps {{
    display: flex;
    align-items: flex-start;
    gap: 0.5rem;
  }}
  .step {{
    flex: 1;
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
  }}
  .step-num {{
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: #334155;
    color: #e2e8f0;
    font-size: 0.8rem;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .step-content {{ flex: 1; }}
  .step-label {{ font-weight: 600; font-size: 0.85rem; margin-bottom: 0.25rem; }}
  .step-desc {{ color: #94a3b8; font-size: 0.78rem; line-height: 1.5; }}
  .step-arrow {{
    flex-shrink: 0;
    color: #475569;
    font-size: 1.25rem;
    padding-top: 0.2rem;
  }}

  @media (max-width: 640px) {{
    .stats-row {{ grid-template-columns: 1fr; }}
    .how-steps {{ flex-direction: column; }}
    .step-arrow {{ transform: rotate(90deg); align-self: center; }}
  }}
</style>
</head>
<body>
<div class="container">

  <h1>Autoresearch: Theme Detection Optimization</h1>
  <p class="subtitle">Optimizing research paper classification using embedding-based discrimination scoring</p>

  <div class="chart-container">
    {svg_chart}
  </div>

  <div class="how-it-works">
    <div class="how-title">How each iteration works</div>
    <div class="how-steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-content">
          <div class="step-label">Mutate</div>
          <div class="step-desc">Ask the LLM to suggest a change to the theme detection prompt (e.g., "add MECE requirement", "ask for keywords per theme").</div>
        </div>
      </div>
      <div class="step-arrow">&rarr;</div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-content">
          <div class="step-label">Detect</div>
          <div class="step-desc">Send the mutated prompt + all paper titles and abstracts to the LLM. It creates research themes and assigns each paper to 1-2 themes.</div>
        </div>
      </div>
      <div class="step-arrow">&rarr;</div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-content">
          <div class="step-label">Score</div>
          <div class="step-desc">Compute S = mean_intra / mean_inter using paper embeddings. No LLM involved, pure math.</div>
        </div>
      </div>
      <div class="step-arrow">&rarr;</div>
      <div class="step">
        <div class="step-num">4</div>
        <div class="step-content">
          <div class="step-label">Keep or revert</div>
          <div class="step-desc">If score improved, keep the new prompt. If not, revert to the previous one.</div>
        </div>
      </div>
    </div>
  </div>

  <div class="formula-box">
<span class="highlight">Score = mean_intra / mean_inter</span>

mean_intra = average cosine similarity between papers within the same theme (coherence)
mean_inter = average cosine similarity between theme centroids (distinctness)

Higher score = themes are internally coherent AND distinct from each other.
A score of 1.0 means themes are no better than random grouping.
  </div>

  <div class="stats-row">
    <div class="stat-card">
      <div class="label">Best Score</div>
      <div class="value green">{best_score:.4f}</div>
      <div class="detail green">+{improvement_pct:.1f}% vs baseline</div>
    </div>
    <div class="stat-card">
      <div class="label">Total Cost</div>
      <div class="value">${total_cost:.4f}</div>
    </div>
    <div class="stat-card">
      <div class="label">Iterations</div>
      <div class="value">{kept_count} kept / {total_count} total</div>
    </div>
  </div>

  <div class="table-container">
    <table>
      <thead>
        <tr>
          <th>Iter</th>
          <th>Score</th>
          <th>Intra</th>
          <th>Inter</th>
          <th>Themes</th>
          <th>Status</th>
          <th>Cost</th>
          <th>Mutation</th>
        </tr>
      </thead>
      <tbody>
        {iterations_rows}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>"""


# ============================================================================
# SVG CHART
# ============================================================================

def build_svg_chart(iterations, baseline_score):
    scores = [it["score"] for it in iterations]
    kept_flags = [it["kept"] for it in iterations]
    n = len(iterations)

    # Compute "best so far" stepped line
    best_so_far = []
    current_best = baseline_score
    for it in iterations:
        if it["kept"]:
            current_best = it["score"]
        best_so_far.append(current_best)

    all_values = scores + [baseline_score]
    y_min = min(all_values) - 0.05
    y_max = max(all_values) + 0.05

    plot_w = CHART_WIDTH - CHART_PADDING_LEFT - CHART_PADDING_RIGHT
    plot_h = CHART_HEIGHT - CHART_PADDING_TOP - CHART_PADDING_BOTTOM

    def x_pos(i):
        return CHART_PADDING_LEFT + (i / max(n - 1, 1)) * plot_w

    def y_pos(val):
        return CHART_PADDING_TOP + (1 - (val - y_min) / (y_max - y_min)) * plot_h

    # Baseline dashed line
    baseline_y = y_pos(baseline_score)

    # Score line points
    score_points = " ".join(f"{x_pos(i):.1f},{y_pos(s):.1f}" for i, s in enumerate(scores))

    # Best-so-far stepped line
    best_path_parts = []
    for i in range(n):
        bx = x_pos(i)
        by = y_pos(best_so_far[i])
        if i == 0:
            best_path_parts.append(f"M {bx:.1f} {by:.1f}")
        else:
            # Horizontal then vertical (stepped)
            best_path_parts.append(f"L {bx:.1f} {y_pos(best_so_far[i-1]):.1f}")
            best_path_parts.append(f"L {bx:.1f} {by:.1f}")
    best_path = " ".join(best_path_parts)

    # Dots
    dots_svg = ""
    for i in range(n):
        cx = x_pos(i)
        cy = y_pos(scores[i])
        if kept_flags[i]:
            dots_svg += f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="#22c55e" />\n'
        else:
            dots_svg += (
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="none" stroke="#ef4444" stroke-width="2" />\n'
                f'<line x1="{cx - 3:.1f}" y1="{cy - 3:.1f}" x2="{cx + 3:.1f}" y2="{cy + 3:.1f}" stroke="#ef4444" stroke-width="1.5" />\n'
                f'<line x1="{cx + 3:.1f}" y1="{cy - 3:.1f}" x2="{cx - 3:.1f}" y2="{cy + 3:.1f}" stroke="#ef4444" stroke-width="1.5" />\n'
            )

    # X axis labels
    x_labels = ""
    for i in range(n):
        x_labels += f'<text x="{x_pos(i):.1f}" y="{CHART_HEIGHT - 5}" text-anchor="middle" fill="#94a3b8" font-size="12">{iterations[i]["iteration"]}</text>\n'

    # Y axis labels (5 ticks)
    y_labels = ""
    y_gridlines = ""
    num_ticks = 5
    for t in range(num_ticks + 1):
        val = y_min + (y_max - y_min) * t / num_ticks
        yp = y_pos(val)
        y_labels += f'<text x="{CHART_PADDING_LEFT - 10}" y="{yp + 4:.1f}" text-anchor="end" fill="#94a3b8" font-size="11">{val:.2f}</text>\n'
        y_gridlines += f'<line x1="{CHART_PADDING_LEFT}" y1="{yp:.1f}" x2="{CHART_WIDTH - CHART_PADDING_RIGHT}" y2="{yp:.1f}" stroke="#334155" stroke-width="0.5" />\n'

    return f"""<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" xmlns="http://www.w3.org/2000/svg">
  <!-- Grid -->
  {y_gridlines}
  <!-- Baseline -->
  <line x1="{CHART_PADDING_LEFT}" y1="{baseline_y:.1f}" x2="{CHART_WIDTH - CHART_PADDING_RIGHT}" y2="{baseline_y:.1f}" stroke="#94a3b8" stroke-width="1" stroke-dasharray="6 4" />
  <text x="{CHART_WIDTH - CHART_PADDING_RIGHT + 5}" y="{baseline_y + 4:.1f}" fill="#94a3b8" font-size="11">baseline</text>
  <!-- Best so far (stepped) -->
  <path d="{best_path}" fill="none" stroke="#22c55e" stroke-width="1" stroke-dasharray="3 3" opacity="0.5" />
  <!-- Score line -->
  <polyline points="{score_points}" fill="none" stroke="#e2e8f0" stroke-width="2" />
  <!-- Dots -->
  {dots_svg}
  <!-- Axis labels -->
  {x_labels}
  {y_labels}
</svg>"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_iterations_rows(iterations):
    rows = ""
    for it in iterations:
        status_badge = (
            '<span class="badge badge-kept">KEPT</span>'
            if it["kept"]
            else '<span class="badge badge-reverted">REVERTED</span>'
        )
        mutation_text = it["mutation"]
        if len(mutation_text) > 80:
            mutation_text = mutation_text[:77] + "..."

        rows += f"""<tr>
          <td>{it["iteration"]}</td>
          <td>{it["score"]:.4f}</td>
          <td>{it["mean_intra"]:.4f}</td>
          <td>{it["mean_inter"]:.4f}</td>
          <td>{it["num_themes"]}</td>
          <td>{status_badge}</td>
          <td>${it["cost"]:.4f}</td>
          <td class="mutation-text">{mutation_text}</td>
        </tr>\n"""
    return rows


if __name__ == "__main__":
    main()
