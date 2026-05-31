"""Consolidate every attribution run into one tidy CSV (one row per chunk-call).

This is the single analyzable artifact: load it in pandas/R/Excel to regenerate
every statistic and chart in the report.

  uv run python src/build_csv.py                 # includes verbatim text
  uv run python src/build_csv.py --strip-text    # public version, no source text

Output: publish/data/attributions.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from grade_report import ALIASES, is_hit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "publish" / "data" / "attributions.csv"
ZVI = ALIASES["Zvi Mowshowitz"]

# (input $/M, output $/M). Anthropic published rates; OpenRouter rows use the
# provider-reported _cost when present and fall back to these only if needed.
PRICES = {
    "claude-opus-4-8": (5, 25), "claude-opus-4-7": (5, 25),
    "claude-opus-4-6": (5, 25), "claude-opus-4-5": (5, 25),
    "claude-opus-4-1": (15, 75), "claude-opus-4-0": (15, 75),
    "claude-sonnet-4-6": (3, 15), "claude-sonnet-4-5": (3, 15),
    "claude-sonnet-4-0": (3, 15), "claude-haiku-4-5": (1, 5),
}


def row_cost(rec: dict, model: str) -> float | None:
    if rec.get("_cost") is not None:   # OpenRouter reports actual cost
        return rec["_cost"]
    u = rec.get("_usage")
    if not u or model not in PRICES:
        return None
    pin, pout = PRICES[model]
    return u.get("in", 0) * pin / 1e6 + u.get("out", 0) * pout / 1e6

# (results file, true author, model, provider). Files absent on disk are skipped.
RUNS = [
    ("results.jsonl",          "Zvi Mowshowitz",  "claude-opus-4-8", "anthropic"),
    ("results_opus45.jsonl",   "Zvi Mowshowitz",  "claude-opus-4-5", "anthropic"),
    ("results_gpt55.jsonl",    "Zvi Mowshowitz",  "openai/gpt-5.5",  "openrouter"),
    ("results_sonnet46.jsonl", "Zvi Mowshowitz",  "claude-sonnet-4-6", "anthropic"),
    ("results_sonnet40.jsonl", "Zvi Mowshowitz",  "claude-sonnet-4-0", "anthropic"),
    ("results_deepseek_pro.jsonl",   "Zvi Mowshowitz", "deepseek/deepseek-v4-pro",   "openrouter"),
    ("results_deepseek_flash.jsonl", "Zvi Mowshowitz", "deepseek/deepseek-v4-flash", "openrouter"),
    ("results_willison.jsonl", "Simon Willison",  "claude-opus-4-8", "anthropic"),
    ("results_scott.jsonl",    "Scott Alexander", "claude-opus-4-8", "anthropic"),
    ("results_douthat.jsonl",  "Ross Douthat",    "claude-opus-4-8", "anthropic"),
    ("results_krugman.jsonl",  "Paul Krugman",    "claude-opus-4-8", "anthropic"),
    ("results_gruber.jsonl",   "John Gruber",     "claude-opus-4-8", "anthropic"),
]

COLUMNS = [
    "true_author", "provider", "model", "thinking", "chunk_id", "kind",
    "n_words", "paragraph_id", "trial", "guess", "confidence",
    "is_specific_person", "hit", "attributed_to_zvi", "refused",
    "input_tokens", "output_tokens", "cost_usd", "reasoning", "text",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strip-text", action="store_true", help="omit verbatim chunk text (public release)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in COLUMNS if not (args.strip_text and c == "text")]

    n_rows = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for fname, author, model, provider in RUNS:
            path = DATA / fname
            if not path.exists():
                print(f"  skip (missing): {fname}")
                continue
            aliases = ALIASES[author]
            count = 0
            for line in open(path):
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                refused = bool(r.get("error"))
                guess = r.get("author_guess", "")
                u = r.get("_usage", {})
                cost = row_cost(r, r.get("model", model))
                row = {
                    "true_author": author,
                    "provider": r.get("provider", provider),
                    "model": r.get("model", model),
                    "thinking": r.get("thinking", ""),
                    "chunk_id": r.get("id"),
                    "kind": r.get("kind"),
                    "n_words": r.get("n_words"),
                    "paragraph_id": r.get("paragraph_id"),
                    "trial": r.get("trial", 0),
                    "guess": "" if refused else guess,
                    "confidence": "" if refused else r.get("confidence"),
                    "is_specific_person": "" if refused else r.get("is_specific_person"),
                    "hit": "" if refused else int(is_hit(guess, aliases)),
                    "attributed_to_zvi": "" if refused else int(is_hit(guess, ZVI)),
                    "refused": int(refused),
                    "input_tokens": u.get("in", ""),
                    "output_tokens": u.get("out", ""),
                    "cost_usd": round(cost, 6) if cost is not None else "",
                    "reasoning": "" if refused else r.get("reasoning", ""),
                    "text": r.get("text", ""),
                }
                w.writerow(row)
                count += 1
                n_rows += 1
            print(f"  {fname:<26} {author:<16} {model:<16} {count} rows")

    print(f"\nwrote {out_path}  ({n_rows} rows, {len(cols)} cols{', text stripped' if args.strip_text else ''})")


if __name__ == "__main__":
    main()
