"""Run all three steps in sequence."""
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

steps = [
    ("01_fetch_papers.py", "Fetching papers from database..."),
    ("02_detect_themes.py", "Detecting themes via LLM..."),
    ("03_compute_trends.py", "Computing trends..."),
]

for script, msg in steps:
    print(f"\n{'='*60}")
    print(msg)
    print(f"{'='*60}\n")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script)],
        cwd=str(SCRIPT_DIR),
    )
    if result.returncode != 0:
        print(f"FAILED: {script} exited with code {result.returncode}")
        sys.exit(1)

print(f"\n{'='*60}")
print("All steps complete. Check output/ for results.")
print(f"{'='*60}")
