"""For each author, find the word count at which attribution accuracy crosses
50% and 80%, via a 1-D logistic regression of hit/miss on chunk word count.

P(hit) = sigmoid(a0 + a1 * z),  z = standardized word count.
Crossing point for probability p:  w = mean + sd * (logit(p) - a0) / a1.

Pure-Python IRLS (Newton-Raphson) fit -- no numpy/sklearn dependency.
Prints a table; also importable (compute_thresholds) for the HTML report.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from grade_report import ALIASES, is_hit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SOURCES = [
    ("Zvi Mowshowitz", "results.jsonl", "Zvi Mowshowitz"),
    ("Simon Willison", "results_willison.jsonl", "Simon Willison"),
    ("Scott Alexander", "results_scott.jsonl", "Scott Alexander"),
    ("Ross Douthat", "results_douthat.jsonl", "Ross Douthat"),
    ("Paul Krugman", "results_krugman.jsonl", "Paul Krugman"),
    ("John Gruber", "results_gruber.jsonl", "John Gruber"),
    ("Matt Levine", "results_levine.jsonl", "Matt Levine"),
    ("George Saunders", "results_saunders.jsonl", "George Saunders"),
]


def sigmoid(x: float) -> float:
    if x < -700:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def logistic_fit(words: list[float], hits: list[int], iters: int = 50):
    """1-D logistic regression via IRLS on standardized word count.
    Returns (a0, a1, mean, sd) or None if degenerate."""
    n = len(words)
    if n < 8 or len(set(hits)) < 2:
        return None
    mean = sum(words) / n
    sd = (sum((w - mean) ** 2 for w in words) / n) ** 0.5
    if sd == 0:
        return None
    z = [(w - mean) / sd for w in words]
    a0, a1 = 0.0, 0.0
    for _ in range(iters):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for zi, yi in zip(z, hits):
            p = sigmoid(a0 + a1 * zi)
            w = max(p * (1 - p), 1e-9)
            r = yi - p
            g0 += r; g1 += r * zi
            h00 += w; h01 += w * zi; h11 += w * zi * zi
        det = h00 * h11 - h01 * h01
        if abs(det) < 1e-12:
            break
        d0 = (h11 * g0 - h01 * g1) / det
        d1 = (h00 * g1 - h01 * g0) / det
        a0 += d0; a1 += d1
        if abs(d0) < 1e-8 and abs(d1) < 1e-8:
            break
    return a0, a1, mean, sd


def crossing(fit, p: float) -> float | None:
    a0, a1, mean, sd = fit
    if a1 <= 0:
        return None  # accuracy not increasing with length -> no meaningful crossing
    logit = math.log(p / (1 - p))
    return mean + sd * (logit - a0) / a1


def compute_thresholds() -> list[dict]:
    out = []
    for label, fname, author in SOURCES:
        path = DATA / fname
        if not path.exists():
            continue
        words, hits = [], []
        for line in open(path):
            r = json.loads(line)
            if r.get("error"):
                continue
            words.append(float(r["n_words"]))
            hits.append(1 if is_hit(r.get("author_guess", ""), ALIASES[author]) else 0)
        fit = logistic_fit(words, hits)
        wmax = max(words) if words else 0
        rec = {"label": label, "n": len(words), "max_words": int(wmax),
               "overall": round(100 * sum(hits) / max(len(hits), 1))}
        if fit:
            w50, w80 = crossing(fit, 0.5), crossing(fit, 0.8)
            rec["w50"] = w50
            rec["w80"] = w80
            # flag thresholds that fall outside the observed length range (extrapolated)
            rec["w50_extrap"] = w50 is not None and w50 > wmax
            rec["w80_extrap"] = w80 is not None and w80 > wmax
        out.append(rec)
    return out


def fmt(w, extrap, wmax):
    if w is None:
        return "n/a"
    if w <= 0:
        return "<1 word"
    s = f"{w:.0f} words"
    if extrap:
        s += f" *(extrapolated; data ends at {wmax}w)*".replace("*", "")
    return s


def main():
    rows = compute_thresholds()
    print(f"\n{'author':<18}{'n':>5}{'overall':>9}{'→50% at':>22}{'→80% at':>26}")
    print("-" * 80)
    for r in rows:
        w50 = fmt(r.get("w50"), r.get("w50_extrap"), r["max_words"])
        w80 = fmt(r.get("w80"), r.get("w80_extrap"), r["max_words"])
        print(f"{r['label']:<18}{r['n']:>5}{r['overall']:>8}%{w50:>22}{w80:>26}")
    print("\n* 'extrapolated' = the logistic curve only reaches that accuracy beyond the longest")
    print("  chunk actually present for that author, so treat it as a projection, not an observation.")


if __name__ == "__main__":
    main()
