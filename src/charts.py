"""Generate static PNG charts for the writeup (publish/figures/).

  uv run python src/charts.py

Figures:
  length_curve.png      accuracy vs word count, 6 authors (Opus 4.8)
  calibration.png       confidence vs actual hit rate, Zvi (Opus 4.8)
  cross_attribution.png correct vs misattributed-to-Zvi, per author
  model_comparison.png  cross-model on Zvi: length curves + $/correct-ID + calibration
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from grade_report import ALIASES, is_hit, bucket, BUCKET_ORDER
from build_csv import row_cost

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIG = ROOT / "publish" / "figures"
ZVI = ALIASES["Zvi Mowshowitz"]

AUTHOR_RUNS = [  # all Opus 4.8
    ("results.jsonl", "Zvi Mowshowitz", "Zvi Mowshowitz", "#c2622d"),
    ("results_willison.jsonl", "Simon Willison", "Simon Willison", "#2d6ec2"),
    ("results_scott.jsonl", "Scott Alexander", "Scott Alexander", "#7a4fb5"),
    ("results_krugman.jsonl", "Paul Krugman", "Paul Krugman", "#3a8a55"),
    ("results_gruber.jsonl", "John Gruber", "John Gruber", "#d4a017"),
    ("results_douthat.jsonl", "Ross Douthat", "Ross Douthat", "#9a948a"),
]
MODEL_RUNS = [  # all on Zvi text
    ("results.jsonl", "Opus 4.8", "claude-opus-4-8", "#c2622d"),
    ("results_gpt55.jsonl", "GPT-5.5", "openai/gpt-5.5", "#10a37f"),
    ("results_deepseek_pro.jsonl", "DeepSeek V4 Pro", "deepseek/deepseek-v4-pro", "#4d6bfe"),
    ("results_deepseek_flash.jsonl", "DeepSeek V4 Flash", "deepseek/deepseek-v4-flash", "#9aa8ff"),
    ("results_opus45.jsonl", "Opus 4.5", "claude-opus-4-5", "#e0894f"),
    ("results_sonnet46.jsonl", "Sonnet 4.6", "claude-sonnet-4-6", "#2d6ec2"),
    ("results_sonnet40.jsonl", "Sonnet 4.0", "claude-sonnet-4-0", "#b0392b"),
]

plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white", "axes.facecolor": "#faf8f3"})


def load(fname, author):
    rows = []
    for line in open(DATA / fname):
        r = json.loads(line)
        if r.get("error"):
            continue
        r["hit"] = is_hit(r.get("author_guess", ""), ALIASES[author])
        r["to_zvi"] = is_hit(r.get("author_guess", ""), ZVI)
        rows.append(r)
    return rows


def curve(rows):
    g = defaultdict(list)
    for r in rows:
        g[bucket(r["n_words"])].append(r)
    xs, ys = [], []
    for i, b in enumerate(BUCKET_ORDER):
        if b in g:
            xs.append(i)
            ys.append(100 * sum(x["hit"] for x in g[b]) / len(g[b]))
    return xs, ys


def fig_length_curve():
    plt.figure(figsize=(8, 5))
    for fname, label, author, col in AUTHOR_RUNS:
        xs, ys = curve(load(fname, author))
        plt.plot(xs, ys, marker="o", color=col, label=label,
                 linestyle="--" if author == "Ross Douthat" else "-")
    plt.xticks(range(len(BUCKET_ORDER)), BUCKET_ORDER)
    plt.ylim(0, 100); plt.xlabel("chunk length (words)"); plt.ylabel("% correctly attributed")
    plt.title("Attribution accuracy vs. chunk length (Opus 4.8)")
    plt.legend(fontsize=9); plt.tight_layout(); plt.savefig(FIG / "length_curve.png", dpi=150); plt.close()


def fig_calibration():
    rows = load("results.jsonl", "Zvi Mowshowitz")
    bins = defaultdict(list)
    for r in rows:
        bins[min(int(r.get("confidence", 0)) // 20 * 20, 80)].append(r["hit"])
    bands = [0, 20, 40, 60, 80]; labels = ["0–19", "20–39", "40–59", "60–79", "80–99"]
    vals = [100 * sum(bins[b]) / len(bins[b]) if bins[b] else 0 for b in bands]
    plt.figure(figsize=(7, 5))
    plt.bar(labels, vals, color="#c2622d", zorder=3)
    plt.plot(labels, [10, 30, 50, 70, 90], "--", color="#666", label="perfect calibration")
    plt.ylim(0, 100); plt.xlabel("model's stated confidence"); plt.ylabel("actual % correct")
    plt.title("Calibration — Opus 4.8 on Zvi (it knows when it knows)")
    plt.legend(); plt.tight_layout(); plt.savefig(FIG / "calibration.png", dpi=150); plt.close()


def fig_cross_attribution():
    labels, correct, tozvi = [], [], []
    for fname, label, author, col in AUTHOR_RUNS:
        rows = load(fname, author)
        labels.append(label)
        correct.append(100 * sum(r["hit"] for r in rows) / len(rows))
        tozvi.append(None if author == "Zvi Mowshowitz" else 100 * sum(r["to_zvi"] for r in rows) / len(rows))
    x = range(len(labels)); w = 0.38
    plt.figure(figsize=(9, 5))
    plt.bar([i - w / 2 for i in x], correct, w, color="#c2622d", label="correctly identified", zorder=3)
    plt.bar([i + w / 2 for i in x], [v if v is not None else 0 for v in tozvi], w,
            color="#7a4fb5", label="mis-attributed to Zvi", zorder=3)
    plt.xticks(list(x), labels, rotation=20, ha="right")
    plt.ylim(0, 100); plt.ylabel("% of that author's chunks")
    plt.title("Style, not tribe or topic: only same-topic Willison is mistaken for Zvi")
    plt.legend(); plt.tight_layout(); plt.savefig(FIG / "cross_attribution.png", dpi=150); plt.close()


def fig_model_comparison():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    cost_per_id = []
    for fname, label, model, col in MODEL_RUNS:
        rows = load(fname, "Zvi Mowshowitz")
        xs, ys = curve(rows)
        ax1.plot(xs, ys, marker="o", color=col, label=label)
        hits = sum(r["hit"] for r in rows)
        cost = sum((row_cost(r, model) or 0) for r in rows)
        cost_per_id.append((label, cost / max(hits, 1), col))
    ax1.set_xticks(range(len(BUCKET_ORDER))); ax1.set_xticklabels(BUCKET_ORDER)
    ax1.set_ylim(0, 100); ax1.set_xlabel("chunk length (words)"); ax1.set_ylabel("% correct (Zvi)")
    ax1.set_title("Capability: accuracy vs length, by model"); ax1.legend(fontsize=9)
    cost_per_id.sort(key=lambda t: t[1])
    ax2.bar([t[0] for t in cost_per_id], [t[1] for t in cost_per_id],
            color=[t[2] for t in cost_per_id], zorder=3)
    ax2.set_ylabel("$ per correct identification"); ax2.set_title("Cost efficiency (lower is better)")
    ax2.tick_params(axis="x", rotation=20)
    for i, t in enumerate(cost_per_id):
        ax2.text(i, t[1], f"${t[1]:.3f}", ha="center", va="bottom", fontsize=9)
    plt.tight_layout(); plt.savefig(FIG / "model_comparison.png", dpi=150); plt.close()


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    fig_length_curve(); fig_calibration(); fig_cross_attribution(); fig_model_comparison()
    print(f"wrote 4 figures to {FIG}")


if __name__ == "__main__":
    main()
