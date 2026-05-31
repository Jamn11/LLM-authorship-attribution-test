"""Grade attribution results against the true author and print a report.

Grading is a transparent alias match: a guess is correct if it contains any of
the true author's aliases (name, surname, blog name). No LLM judge -> no leniency
drift, fully reproducible. Inspect/extend ALIASES as needed.

Reports, split by chunk kind and by length bucket:
  * hit rate (correctly named the true author)
  * "specific person" rate and mean confidence
  * accuracy-vs-length curve (where does ID become possible?)
  * calibration (confidence vs. actual hit rate)
  * the top wrong guesses (who it confuses the author with)
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# True-author aliases. Key = canonical name passed via --author.
# Precise-name matches only -- blog names ("Don't Worry About the Vacuum", etc.)
# deliberately excluded so a hit means the model named the PERSON.
ALIASES = {
    "Zvi Mowshowitz": ["zvi", "mowshowitz"],
    "Ross Douthat": ["douthat"],
    "Scott Alexander": ["scott alexander", "siskind"],  # NB: not "scott aaronson"
    "Simon Willison": ["simon willison", "willison"],
    "Paul Krugman": ["krugman"],
    "John Gruber": ["gruber"],
    "Matt Levine": ["matt levine", "levine"],
    "George Saunders": ["george saunders", "saunders"],
}


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())


def is_hit(guess: str, aliases: list[str]) -> bool:
    g = normalize(guess)
    return any(a in g for a in aliases)


def bucket(n: int) -> str:
    for lo, hi in [(1, 3), (4, 6), (7, 10), (11, 20), (21, 35), (36, 60), (61, 9999)]:
        if lo <= n <= hi:
            return f"{lo}-{hi if hi < 9999 else '+'}".replace("-+", "+")
    return "?"


BUCKET_ORDER = ["1-3", "4-6", "7-10", "11-20", "21-35", "36-60", "61+"]


def bar(frac: float, width: int = 24) -> str:
    n = round(frac * width)
    return "█" * n + "·" * (width - n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(DATA / "results.jsonl"))
    ap.add_argument("--author", default="Zvi Mowshowitz")
    ap.add_argument("--show-misses", type=int, default=0, help="print N longest missed chunks")
    args = ap.parse_args()

    aliases = ALIASES.get(args.author, [normalize(args.author)] + normalize(args.author).split())
    rows = []
    for line in open(args.results):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if "error" in r:
            continue
        r["hit"] = is_hit(r.get("author_guess", ""), aliases)
        rows.append(r)

    if not rows:
        print("no gradeable results.")
        return

    print(f"\n{'='*70}\nAuthorship attribution report  --  true author: {args.author}")
    print(f"results: {args.results}   gradeable rows: {len(rows)}\n{'='*70}")

    # Overall + by kind
    for kind in ["paragraph", "sentence"]:
        sub = [r for r in rows if r["kind"] == kind]
        if not sub:
            continue
        hits = sum(r["hit"] for r in sub)
        named = sum(r.get("is_specific_person", False) for r in sub)
        conf = sum(r.get("confidence", 0) for r in sub) / len(sub)
        print(f"\n## {kind.upper()}S  (n={len(sub)})")
        print(f"   hit rate (named {args.author}): {hits}/{len(sub)} = {hits/len(sub):.1%}")
        print(f"   gave a specific person:        {named/len(sub):.1%}    mean confidence: {conf:.0f}")

        # accuracy vs length
        by_b = defaultdict(list)
        for r in sub:
            by_b[bucket(r["n_words"])].append(r)
        print("   hit rate by word-count:")
        for b in BUCKET_ORDER:
            if b in by_b:
                g = by_b[b]
                h = sum(x["hit"] for x in g)
                print(f"     {b:>6} words  n={len(g):>3}  {bar(h/len(g))} {h/len(g):.0%}")

    # Calibration (all rows)
    print(f"\n## CALIBRATION  (confidence vs. actual hit rate, all chunks)")
    cal = defaultdict(list)
    for r in rows:
        band = min(int(r.get("confidence", 0)) // 20 * 20, 80)
        cal[band].append(r["hit"])
    for band in range(0, 100, 20):
        if band in cal:
            g = cal[band]
            print(f"   conf {band:>2}-{band+19}  n={len(g):>3}  actual hit {sum(g)/len(g):.0%}")

    # Confusions
    print(f"\n## TOP WRONG GUESSES (who it confuses the author with)")
    wrong = Counter(r.get("author_guess", "?") for r in rows if not r["hit"])
    for name, c in wrong.most_common(8):
        print(f"   {c:>3}  {name}")

    if args.show_misses:
        print(f"\n## LONGEST MISSED CHUNKS")
        misses = sorted([r for r in rows if not r["hit"]], key=lambda r: -r["n_words"])
        for r in misses[: args.show_misses]:
            print(f"   [{r['n_words']}w conf={r.get('confidence')}] guess={r.get('author_guess')!r}")
            print(f"       {r['text'][:160]}")


if __name__ == "__main__":
    main()
