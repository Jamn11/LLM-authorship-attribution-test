"""Rescore WITHOUT re-running the API: filter every results file to the clean
chunk set produced by the fixed scraper (TOC/navigation removed, no <li>/<p>
double-count), keeping one row per unique (text, kind).

Backs up the originals to data/_prededup_backup/ first. No model calls.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BACKUP = DATA / "_prededup_backup"

# results file -> the (already re-scraped, clean) chunks file defining its corpus
RESULTS_TO_CHUNKS = {
    "results.jsonl": "chunks.json",
    "results_opus45.jsonl": "chunks.json",
    "results_gpt55.jsonl": "chunks.json",
    "results_sonnet46.jsonl": "chunks.json",
    "results_sonnet40.jsonl": "chunks.json",
    "results_deepseek_pro.jsonl": "chunks.json",
    "results_deepseek_flash.jsonl": "chunks.json",
    "results_willison.jsonl": "chunks_willison.json",
    "results_scott.jsonl": "chunks_scott.json",
    "results_douthat.jsonl": "chunks_douthat.json",
    "results_krugman.jsonl": "chunks_krugman.json",
    "results_gruber.jsonl": "chunks_gruber.json",
}


def clean_set(chunks_file):
    d = json.load(open(DATA / chunks_file))
    return {(c["text"], c["kind"]) for c in d["chunks"]}


def main():
    BACKUP.mkdir(exist_ok=True)
    print(f"{'file':<30}{'orig':>6}{'kept':>6}{'dropped':>8}")
    for rfile, cfile in RESULTS_TO_CHUNKS.items():
        path = DATA / rfile
        if not path.exists():
            continue
        keep_keys = clean_set(cfile)
        rows = [json.loads(l) for l in open(path)]
        shutil.copy(path, BACKUP / rfile)  # backup raw
        seen = set()
        kept = []
        for r in rows:
            key = (r.get("text", ""), r.get("kind", ""))
            if key in keep_keys and key not in seen:
                seen.add(key)
                kept.append(r)
        with open(path, "w", encoding="utf-8") as f:
            for r in kept:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{rfile:<30}{len(rows):>6}{len(kept):>6}{len(rows)-len(kept):>8}")
    print(f"\nbackups in {BACKUP}")


if __name__ == "__main__":
    main()
