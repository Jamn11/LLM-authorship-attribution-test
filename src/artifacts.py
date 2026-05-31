"""Generate the writeup data artifacts: comparison tables (markdown + CSV),
the words-to-50%-over-time graph, per-pairing accuracy curves, and a
calibration-by-model figure.

  uv run python src/artifacts.py

Outputs into publish/data/ (tables) and publish/figures/ (charts).
Threshold estimates include 90% bootstrap confidence intervals.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from grade_report import ALIASES, is_hit, bucket, BUCKET_ORDER
from thresholds import logistic_fit, crossing
from build_csv import row_cost

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PUB = ROOT / "publish"
FIG = PUB / "figures"
CURVES = FIG / "curves"
ZVI = ALIASES["Zvi Mowshowitz"]
random.seed(0)

ZVI_WORK = "Claude Opus 4.8: The System Card"
# Every (run file, model label, model id, release date, author, work) pairing we have.
PAIRINGS = [
    ("results.jsonl",          "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "Zvi Mowshowitz",  ZVI_WORK),
    ("results_gpt55.jsonl",    "GPT-5.5",    "openai/gpt-5.5",    "2026-04-23", "Zvi Mowshowitz",  ZVI_WORK),
    ("results_deepseek_pro.jsonl",   "DeepSeek V4 Pro",   "deepseek/deepseek-v4-pro",   "2026-04-23", "Zvi Mowshowitz", ZVI_WORK),
    ("results_deepseek_flash.jsonl", "DeepSeek V4 Flash", "deepseek/deepseek-v4-flash", "2026-04-23", "Zvi Mowshowitz", ZVI_WORK),
    ("results_sonnet46.jsonl", "Sonnet 4.6", "claude-sonnet-4-6", "2026-02-17", "Zvi Mowshowitz",  ZVI_WORK),
    ("results_opus45.jsonl",   "Opus 4.5",   "claude-opus-4-5",   "2025-11-24", "Zvi Mowshowitz",  ZVI_WORK),
    ("results_sonnet40.jsonl", "Sonnet 4.0", "claude-sonnet-4-0", "2025-05-22", "Zvi Mowshowitz",  ZVI_WORK),
    ("results_willison.jsonl", "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "Simon Willison",  "Claude Opus 4.8"),
    ("results_scott.jsonl",    "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "Scott Alexander", "Book Review: The Dialectical Imagination"),
    ("results_krugman.jsonl",  "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "Paul Krugman",    "Europe Versus America: A Response to the Critics"),
    ("results_gruber.jsonl",   "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "John Gruber",     "What Is a Dickover?"),
    ("results_douthat.jsonl",  "Opus 4.8",   "claude-opus-4-8",   "2026-05-28", "Ross Douthat",    "The Best News in America"),
]
MODEL_RUNS = [p for p in PAIRINGS if p[4] == "Zvi Mowshowitz"]
AUTHOR_RUNS = [p for p in PAIRINGS if p[2] == "claude-opus-4-8"]
COLORS = {"Opus 4.8": "#c2622d", "GPT-5.5": "#10a37f", "Sonnet 4.6": "#2d6ec2",
          "Opus 4.5": "#e0894f", "Sonnet 4.0": "#b0392b",
          "DeepSeek V4 Pro": "#4d6bfe", "DeepSeek V4 Flash": "#9aa8ff"}
AUTHOR_COLORS = {"Zvi Mowshowitz": "#c2622d", "Simon Willison": "#2d6ec2", "Scott Alexander": "#7a4fb5",
                 "Paul Krugman": "#3a8a55", "John Gruber": "#d4a017", "Ross Douthat": "#9a948a"}


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


def thresholds_ci(rows, B=200):
    w = [float(r["n_words"]) for r in rows]
    h = [r["hit"] for r in rows]
    fit = logistic_fit(w, h)
    w50, w80 = (crossing(fit, 0.5), crossing(fit, 0.8)) if fit else (None, None)
    boots50, boots80 = [], []
    n = len(rows)
    for _ in range(B):
        idx = [random.randrange(n) for _ in range(n)]
        bw = [w[i] for i in idx]; bh = [h[i] for i in idx]
        bf = logistic_fit(bw, bh)
        if not bf:
            continue
        c50, c80 = crossing(bf, 0.5), crossing(bf, 0.8)
        if c50 and 0 < c50 < 500:
            boots50.append(c50)
        if c80 and 0 < c80 < 500:
            boots80.append(c80)

    def ci(b):
        if len(b) < 20:
            return (None, None)
        b = sorted(b)
        return (b[int(0.05 * len(b))], b[int(0.95 * len(b))])
    return w50, w80, ci(boots50), ci(boots80)


def emp_points(rows):
    g = defaultdict(list)
    for r in rows:
        g[bucket(r["n_words"])].append(r)
    pts = []
    for b in BUCKET_ORDER:
        if b in g:
            grp = g[b]
            mw = sum(x["n_words"] for x in grp) / len(grp)
            pts.append((mw, 100 * sum(x["hit"] for x in grp) / len(grp), len(grp)))
    return pts


def sig(fit, x):
    import math
    a0, a1, mean, sd = fit
    return 100 / (1 + math.exp(-(a0 + a1 * (x - mean) / sd)))


def fnum(v, suffix="w"):
    return "n/a" if v is None else f"{v:.0f}{suffix}"


def fci(ci):
    lo, hi = ci
    return "" if lo is None else f" [{lo:.0f}–{hi:.0f}]"


# ---------------- Tables (each returns (title, header, display-rows) and writes a CSV) ----------------

def table_author():
    header = ["author", "work", "chunks", "words→50% (90% CI)", "words→80% (90% CI)"]
    disp, csv_rows = [], []
    for fname, mlabel, mid, date, author, work in AUTHOR_RUNS:
        rows = load(fname, author)
        w50, w80, c50, c80 = thresholds_ci(rows)
        disp.append([author, work if len(work) <= 34 else work[:33] + "…", str(len(rows)),
                     fnum(w50) + fci(c50), fnum(w80) + fci(c80)])
        csv_rows.append({"author": author, "work": work, "n_chunks": len(rows),
                         "words_to_50": round(w50) if w50 else "", "w50_ci_lo": c50[0] and round(c50[0]),
                         "w50_ci_hi": c50[1] and round(c50[1]),
                         "words_to_80": round(w80) if w80 else "", "w80_ci_lo": c80[0] and round(c80[0]),
                         "w80_ci_hi": c80[1] and round(c80[1])})
    _write_csv("table_opus48_by_author.csv", csv_rows)
    return "Table 1 — Opus 4.8, accuracy thresholds by author", header, disp


def table_model():
    header = ["model", "released", "chunks", "overall", "≥21w", "→50% (90% CI)",
              "→80%", "in tok", "out tok", "cost", "$/correct"]
    disp, csv_rows = [], []
    for fname, mlabel, mid, date, author, work in MODEL_RUNS:
        rows = load(fname, author)
        w50, w80, c50, c80 = thresholds_ci(rows)
        hits = sum(r["hit"] for r in rows)
        lng = [r for r in rows if r["n_words"] >= 21]
        cl = sum(r["hit"] for r in lng)
        it = sum(r.get("_usage", {}).get("in", 0) for r in rows)
        ot = sum(r.get("_usage", {}).get("out", 0) for r in rows)
        cost = sum((row_cost(r, mid) or 0) for r in rows)
        disp.append([mlabel, date, str(len(rows)), f"{hits/len(rows)*100:.0f}%", f"{cl/len(lng)*100:.0f}%",
                     fnum(w50) + fci(c50), fnum(w80), f"{it:,}", f"{ot:,}", f"${cost:.2f}", f"${cost/max(hits,1):.3f}"])
        csv_rows.append({"model": mlabel, "model_id": mid, "released": date, "n_chunks": len(rows),
                         "overall_acc": round(hits/len(rows)*100), "acc_ge21w": round(cl/len(lng)*100),
                         "words_to_50": round(w50) if w50 else "", "words_to_80": round(w80) if w80 else "",
                         "input_tokens": it, "output_tokens": ot, "cost_usd": round(cost, 2),
                         "cost_per_correct_id": round(cost/max(hits, 1), 4)})
    _write_csv("table_models_zvi.csv", csv_rows)
    return "Table 2 — Cross-model on the Zvi post", header, disp


def table_cross_attr():
    from collections import Counter
    header = ["author", "role", "topic", "correct", "→ Zvi", "top wrong guesses"]
    roles = {"Zvi Mowshowitz": ("target", "AI / Opus 4.8"), "Simon Willison": ("same-topic", "AI / Opus 4.8"),
             "Scott Alexander": ("same-tribe", "book review"), "Paul Krugman": ("control", "economics"),
             "John Gruber": ("control", "tech"), "Ross Douthat": ("control", "politics")}
    disp, csv_rows = [], []
    for fname, mlabel, mid, date, author, work in AUTHOR_RUNS:
        rows = load(fname, author)
        correct = 100 * sum(r["hit"] for r in rows) / len(rows)
        tozvi = 100 * sum(r["to_zvi"] for r in rows) / len(rows)
        wrong = Counter(r.get("author_guess", "?") for r in rows if not r["hit"]).most_common(3)
        role, topic = roles[author]
        tz = "—" if author == "Zvi Mowshowitz" else f"{tozvi:.0f}%"
        disp.append([author, role, topic, f"{correct:.0f}%", tz, ", ".join(g for g, _ in wrong)])
        csv_rows.append({"author": author, "role": role, "topic": topic, "correct_pct": round(correct),
                         "attributed_to_zvi_pct": round(tozvi),
                         "top_wrong_guesses": "; ".join(f"{g}({n})" for g, n in wrong)})
    _write_csv("table_cross_attribution.csv", csv_rows)
    return "Table 3 — Style vs. tribe vs. topic (Opus 4.8)", header, disp


def _write_csv(name, rows):
    if not rows:
        return
    with open(PUB / "data" / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)


def md_table(header, rows):
    return ("| " + " | ".join(header) + " |\n"
            + "|" + "|".join("---" for _ in header) + "|\n"
            + "\n".join("| " + " | ".join(r) + " |" for r in rows))


def png_table(title, header, rows, fname):
    ncol = len(header)
    widths = [max(len(str(header[c])), *(len(str(r[c])) for r in rows)) + 2 for c in range(ncol)]
    total = sum(widths)
    fig, ax = plt.subplots(figsize=(max(7, total * 0.115), 0.55 + 0.45 * (len(rows) + 1)))
    ax.axis("off")
    tbl = ax.table(cellText=rows, colLabels=header, cellLoc="center", loc="center",
                   colWidths=[w / total for w in widths])
    tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.45)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#e4e0d8")
        if r == 0:
            cell.set_facecolor("#c2622d"); cell.get_text().set_color("white"); cell.get_text().set_fontweight("bold")
        else:
            cell.set_facecolor("#ffffff" if r % 2 else "#f5f1e8")
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left", pad=12, color="#1a1a1a")
    plt.savefig(FIG / fname, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close()


# ---------------- Figures ----------------

def fig_over_time():
    plt.figure(figsize=(8, 5.2))
    fam = {"Opus 4.8": "Anthropic Opus", "Opus 4.5": "Anthropic Opus",
           "Sonnet 4.6": "Anthropic Sonnet", "Sonnet 4.0": "Anthropic Sonnet", "GPT-5.5": "OpenAI",
           "DeepSeek V4 Pro": "DeepSeek", "DeepSeek V4 Flash": "DeepSeek"}
    import datetime
    pts = []
    for fname, mlabel, mid, date, author, work in MODEL_RUNS:
        rows = load(fname, author)
        w50, _, _, _ = thresholds_ci(rows, B=1)
        d = datetime.date.fromisoformat(date)
        pts.append((d, w50, mlabel, fam[mlabel]))
    # connect within family
    for family, style in [("Anthropic Opus", "-"), ("Anthropic Sonnet", "-"), ("OpenAI", ""), ("DeepSeek", "-")]:
        fp = sorted([p for p in pts if p[3] == family])
        if len(fp) > 1:
            plt.plot([p[0] for p in fp], [p[1] for p in fp], style, color="#bbb", zorder=1)
    for d, w50, label, family in pts:
        plt.scatter([d], [w50], s=90, color=COLORS[label], zorder=3)
        plt.annotate(f"{label}\n{w50:.0f}w", (d, w50), textcoords="offset points",
                     xytext=(8, 6), fontsize=9)
    plt.gca().invert_yaxis()  # fewer words = better -> up
    plt.ylabel("words needed to reach 50% accuracy  (lower = better)")
    plt.xlabel("model release date")
    plt.title("Authorship identifiability over time (Zvi post)\nNewer models need fewer words")
    plt.tight_layout(); plt.savefig(FIG / "words_to_50_over_time.png", dpi=150); plt.close()


def fig_calibration_by_model():
    plt.figure(figsize=(8, 5))
    bands = [0, 20, 40, 60, 80]; labels = ["0–19", "20–39", "40–59", "60–79", "80–99"]
    for fname, mlabel, mid, date, author, work in MODEL_RUNS:
        rows = load(fname, author)
        bins = defaultdict(list)
        for r in rows:
            bins[min(int(r.get("confidence", 0)) // 20 * 20, 80)].append(r["hit"])
        ys = [100 * sum(bins[b]) / len(bins[b]) if bins[b] else None for b in bands]
        plt.plot(labels, ys, marker="o", color=COLORS[mlabel], label=mlabel)
    plt.plot(labels, [10, 30, 50, 70, 90], "--", color="#888", label="perfect")
    plt.ylim(0, 100); plt.xlabel("stated confidence"); plt.ylabel("actual % correct")
    plt.title("Calibration by model (Zvi post) — older models are confidently wrong")
    plt.legend(fontsize=9); plt.tight_layout(); plt.savefig(FIG / "calibration_by_model.png", dpi=150); plt.close()


def fig_pairing_curves():
    CURVES.mkdir(parents=True, exist_ok=True)
    for fname, mlabel, mid, date, author, work in PAIRINGS:
        rows = load(fname, author)
        fit = logistic_fit([float(r["n_words"]) for r in rows], [r["hit"] for r in rows])
        pts = emp_points(rows)
        plt.figure(figsize=(6.2, 4.2))
        col = COLORS.get(mlabel, "#333") if author == "Zvi Mowshowitz" else AUTHOR_COLORS.get(author, "#333")
        plt.scatter([p[0] for p in pts], [p[1] for p in pts],
                    s=[max(20, p[2]) for p in pts], color=col, alpha=0.6, zorder=3, label="observed (by length bucket)")
        if fit and fit[1] > 0:
            xmax = max(r["n_words"] for r in rows)
            xs = [x for x in range(1, int(xmax) + 1)]
            plt.plot(xs, [sig(fit, x) for x in xs], color=col, lw=2, label="logistic fit")
            for p, y in [(0.5, "50%"), (0.8, "80%")]:
                wc = crossing(fit, p)
                if wc and 0 < wc <= xmax:
                    plt.axvline(wc, ls=":", color="#999")
                    plt.text(wc, 5, f"{y}: {wc:.0f}w", rotation=90, fontsize=8, va="bottom")
        plt.ylim(0, 100); plt.xlabel("chunk length (words)"); plt.ylabel("% correct")
        plt.title(f"{mlabel} — {author}\n{work[:48]}", fontsize=10)
        plt.legend(fontsize=8, loc="lower right"); plt.tight_layout()
        slug = mid.replace("/", "-").replace(".", "-") + "__" + author.split()[-1].lower()
        plt.savefig(CURVES / f"{slug}.png", dpi=130); plt.close()


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    tables = [("table_models_zvi.png", table_model()),
              ("table_opus48_by_author.png", table_author()),
              ("table_cross_attribution.png", table_cross_attr())]
    md = ["# LLM authorship-attribution test — comparison tables\n",
          "_Threshold estimates from logistic fits; brackets are 90% bootstrap CIs (200 resamples)._\n"]
    for pngname, (title, header, rows) in tables:
        md.append(f"### {title}\n\n" + md_table(header, rows) + "\n")
        png_table(title, header, rows, pngname)
    (PUB / "data" / "tables.md").write_text("\n".join(md), encoding="utf-8")
    fig_over_time(); fig_calibration_by_model(); fig_pairing_curves()
    print("wrote publish/data/tables.md + table_*.csv + table_*.png (rendered images)")
    print(f"wrote figures: words_to_50_over_time, calibration_by_model, {len(PAIRINGS)} pairing curves")
    print("\n" + (PUB / "data" / "tables.md").read_text())


if __name__ == "__main__":
    main()
