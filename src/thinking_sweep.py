"""Run a fixed subset of chunks through every thinking level and compare.

Answers: does thinking/effort level change attribution accuracy, confidence, or
cost much? Same chunks at none/low/medium/high/xhigh, graded against the author.

Writes data/thinking_sweep.jsonl (all raw rows) and prints a comparison table.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from run_attribution import attribute_once, THINKING_LEVELS, MODEL
from grade_report import ALIASES, is_hit

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"


def stratified_subset(chunks: list[dict], n: int) -> list[dict]:
    """Deterministic sample spanning the word-count range, both kinds represented."""
    ordered = sorted(chunks, key=lambda c: (c["n_words"], c["id"]))
    if len(ordered) <= n:
        return ordered
    step = len(ordered) / n
    return [ordered[int(i * step)] for i in range(n)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default=str(DATA / "chunks.json"))
    ap.add_argument("--out", default=str(DATA / "thinking_sweep.jsonl"))
    ap.add_argument("--author", default="Zvi Mowshowitz")
    ap.add_argument("--n", type=int, default=40, help="chunks in the subset")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    aliases = ALIASES.get(args.author, [])
    data = json.load(open(args.chunks))
    subset = stratified_subset(data["chunks"], args.n)
    print(f"model={MODEL}  subset={len(subset)} chunks  levels={THINKING_LEVELS}  "
          f"total calls={len(subset)*len(THINKING_LEVELS)}")

    client = Anthropic()
    jobs = [(c, lvl) for lvl in THINKING_LEVELS for c in subset]
    rows = []
    out_f = open(args.out, "w", encoding="utf-8")
    t0 = time.time()

    def work(job):
        chunk, lvl = job
        return chunk, lvl, attribute_once(chunk["text"], lvl, client=client)

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for fut in as_completed(futs):
            chunk, lvl, res = fut.result()
            rec = {"id": chunk["id"], "kind": chunk["kind"], "n_words": chunk["n_words"],
                   "thinking": lvl, "text": chunk["text"], **res}
            rec["hit"] = (not res.get("error")) and is_hit(res.get("author_guess", ""), aliases)
            rows.append(rec)
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            done += 1
            if done % 25 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}  {done/max(time.time()-t0,1e-6):.1f}/s")
    out_f.close()

    # Per-level aggregates
    print(f"\n{'='*72}\nTHINKING-LEVEL COMPARISON  (true author: {args.author}, n={len(subset)} chunks)\n{'='*72}")
    print(f"{'level':<8}{'hit rate':>12}{'mean conf':>12}{'mean out tok':>14}{'errors':>9}")
    by_level = {lvl: [r for r in rows if r["thinking"] == lvl] for lvl in THINKING_LEVELS}
    for lvl in THINKING_LEVELS:
        g = by_level[lvl]
        ok = [r for r in g if not r.get("error")]
        errs = len(g) - len(ok)
        hits = sum(r["hit"] for r in ok)
        conf = sum(r.get("confidence", 0) for r in ok) / max(len(ok), 1)
        otok = sum(r.get("_usage", {}).get("out", 0) for r in ok) / max(len(ok), 1)
        hr = f"{hits}/{len(ok)} ({hits/max(len(ok),1):.0%})"
        print(f"{lvl:<8}{hr:>12}{conf:>12.0f}{otok:>14.0f}{errs:>9}")

    # Per-chunk stability: how often does the guess flip across levels?
    by_chunk = defaultdict(dict)
    for r in rows:
        if not r.get("error"):
            by_chunk[r["id"]][r["thinking"]] = r["hit"]
    flipped = [cid for cid, d in by_chunk.items() if len(set(d.values())) > 1]
    print(f"\nchunks with identical hit/miss across ALL levels: "
          f"{len(by_chunk)-len(flipped)}/{len(by_chunk)}")
    if flipped:
        print(f"chunks whose correctness changed with thinking level ({len(flipped)}):")
        for cid in flipped[:12]:
            d = by_chunk[cid]
            pattern = " ".join(f"{lvl}={'Y' if d.get(lvl) else 'n'}" for lvl in THINKING_LEVELS if lvl in d)
            txt = next(r["text"] for r in rows if r["id"] == cid)
            print(f"  [{cid}] {pattern}   {txt[:70]!r}")


if __name__ == "__main__":
    main()
