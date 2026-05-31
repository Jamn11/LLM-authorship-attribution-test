"""Regenerate every analysis artifact from the existing run data in data/.

This calls NO API and costs nothing -- it assumes the per-call result files
(data/results*.jsonl) already exist. Produce those first with the model passes:

    uv run python src/run_attribution.py --model claude-opus-4-8 --out data/results.jsonl
    uv run python src/run_attribution.py --provider openrouter --model openai/gpt-5.5 \
        --thinking medium --out data/results_gpt55.jsonl
    ... (see publish/README.md for the full method)

Then:  uv run python main.py
"""
import subprocess
import sys

STEPS = [
    ("consolidated CSV (with text)", ["src/build_csv.py"]),
    ("public CSV (text stripped)", ["src/build_csv.py", "--strip-text",
                                    "--out", "publish/data/attributions_public.csv"]),
    ("core figures", ["src/charts.py"]),
    ("tables + over-time + per-pairing curves", ["src/artifacts.py"]),
    ("interactive report (publish/report.html)", ["src/report_html.py"]),
    ("reasoning audit tool (publish/reasoning_audit.html)", ["src/reasoning_browser.py"]),
]


def main():
    for name, cmd in STEPS:
        print(f"\n=== {name} ===")
        subprocess.run([sys.executable, *cmd], check=True)
    print("\nAll artifacts regenerated. See publish/ for the polished outputs.")


if __name__ == "__main__":
    main()
