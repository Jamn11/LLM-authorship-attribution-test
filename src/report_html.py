"""Render a self-contained HTML report (Chart.js via CDN) from the result files.

Usage: uv run python src/report_html.py   ->  data/report.html

Sources (each a separate run through the identical no-tools pipeline):
  Zvi Mowshowitz   target          AI / Claude Opus 4.8   (post-cutoff)
  Simon Willison   same-topic ctrl AI / Claude Opus 4.8
  Scott Alexander  same-tribe ctrl book review (LessWrong-adjacent, off-topic)
  Ross Douthat     off-everything  crime / politics
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from grade_report import ALIASES, is_hit, bucket, BUCKET_ORDER
from thresholds import compute_thresholds

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ZVI = ALIASES["Zvi Mowshowitz"]

SOURCES = [
    {"key": "zvi", "label": "Zvi Mowshowitz", "file": "results.jsonl",
     "author": "Zvi Mowshowitz", "role": "TARGET", "topic": "AI · Claude Opus 4.8"},
    {"key": "willison", "label": "Simon Willison", "file": "results_willison.jsonl",
     "author": "Simon Willison", "role": "same-topic control", "topic": "AI · Claude Opus 4.8"},
    {"key": "scott", "label": "Scott Alexander", "file": "results_scott.jsonl",
     "author": "Scott Alexander", "role": "same-tribe control", "topic": "book review (LessWrong-adjacent)"},
    {"key": "douthat", "label": "Ross Douthat", "file": "results_douthat.jsonl",
     "author": "Ross Douthat", "role": "off-topic control", "topic": "crime · politics"},
    {"key": "krugman", "label": "Paul Krugman", "file": "results_krugman.jsonl",
     "author": "Paul Krugman", "role": "non-LessWrong control", "topic": "economics"},
    {"key": "gruber", "label": "John Gruber", "file": "results_gruber.jsonl",
     "author": "John Gruber", "role": "non-LessWrong control", "topic": "tech criticism"},
    {"key": "levine", "label": "Matt Levine", "file": "results_levine.jsonl",
     "author": "Matt Levine", "role": "non-LessWrong control", "topic": "finance"},
    {"key": "saunders", "label": "George Saunders", "file": "results_saunders.jsonl",
     "author": "George Saunders", "role": "non-LessWrong control", "topic": "literary fiction"},
]


def load(path: Path, aliases: list[str]) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("error"):
            r["refused"] = True
        else:
            r["hit"] = is_hit(r.get("author_guess", ""), aliases)
            r["to_zvi"] = is_hit(r.get("author_guess", ""), ZVI)
        rows.append(r)
    return rows


def gradeable(rows):
    return [r for r in rows if not r.get("refused")]


def by_bucket(rows):
    g = defaultdict(list)
    for r in rows:
        g[bucket(r["n_words"])].append(r)
    return {b: {"n": len(g[b]), "rate": round(100 * sum(x["hit"] for x in g[b]) / len(g[b]))}
            for b in BUCKET_ORDER if b in g}


def calibration(rows):
    bins = defaultdict(list)
    for r in rows:
        band = min(int(r.get("confidence", 0)) // 20 * 20, 80)
        bins[band].append(r["hit"])
    return {band: {"n": len(v), "rate": round(100 * sum(v) / len(v))} for band, v in sorted(bins.items())}


def rate(rows, key):
    return round(100 * sum(r[key] for r in rows) / max(len(rows), 1))


def kind_rate(rows, kind):
    sub = [r for r in rows if r["kind"] == kind]
    return round(100 * sum(r["hit"] for r in sub) / max(len(sub), 1))


def examples(rows, want_hit, n=6, max_words=None):
    g = [r for r in rows if r["hit"] == want_hit]
    if max_words:
        g = [r for r in g if r["n_words"] <= max_words]
    g.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    return [{"text": r["text"], "guess": r.get("author_guess"), "conf": r.get("confidence"),
             "words": r["n_words"], "kind": r["kind"]} for r in g[:n]]


def main():
    src_data = []
    for s in SOURCES:
        if not (DATA / s["file"]).exists():
            continue  # source not run yet (e.g. paywalled, awaiting paste)
        rows = load(DATA / s["file"], ALIASES[s["author"]])
        g = gradeable(rows)
        src_data.append({
            "key": s["key"], "label": s["label"], "role": s["role"], "topic": s["topic"],
            "n": len(g), "refused": sum(1 for r in rows if r.get("refused")),
            "correct": rate(g, "hit"), "to_zvi": rate(g, "to_zvi"),
            "curve": by_bucket(g),
            "curve_long": rate([r for r in g if r["n_words"] >= 21], "hit"),
            "to_zvi_long": rate([r for r in g if r["n_words"] >= 21], "to_zvi"),
            "calib": calibration(g),
            "confusions": Counter(r.get("author_guess", "?") for r in g if not r["hit"]).most_common(6),
        })

    zvi_rows = gradeable(load(DATA / "results.jsonl", ZVI))
    thresholds = sorted(compute_thresholds(), key=lambda r: r.get("w50") or 1e9)
    payload = {
        "buckets": BUCKET_ORDER,
        "sources": src_data,
        "thresholds": thresholds,
        "zvi_para": kind_rate(zvi_rows, "paragraph"),
        "zvi_sent": kind_rate(zvi_rows, "sentence"),
        "zvi_hits": examples(zvi_rows, True, n=6, max_words=15),
        "zvi_misses": examples(zvi_rows, False, n=6),
    }
    html = HTML_TEMPLATE.replace("/*DATA*/", json.dumps(payload))
    out = ROOT / "publish" / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    for s in src_data:
        print(f"  {s['label']:<18} n={s['n']:<4} →true {s['correct']}%  →Zvi {s['to_zvi']}%  "
              f"(≥21w: →true {s['curve_long']}%, →Zvi {s['to_zvi_long']}%)")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>zvi-sight — Authorship Attribution by Opus 4.8</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{--ink:#1a1a1a;--mut:#6b6b6b;--line:#e4e0d8;--bg:#faf8f3;--card:#fff;--accent:#c2622d;--blue:#2d6ec2;--good:#3a8a55;--purp:#7a4fb5;}
  *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
  .wrap{max-width:980px;margin:0 auto;padding:48px 24px 80px;}
  h1{font-size:34px;line-height:1.15;margin:0 0 6px;letter-spacing:-.02em;}
  h2{font-size:22px;margin:48px 0 14px;letter-spacing:-.01em;border-bottom:2px solid var(--line);padding-bottom:8px;}
  h3{font-size:15px;margin:4px 0 10px;}
  .sub{color:var(--mut);font-size:15px;margin:0 0 28px;}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:24px 0;}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;}
  .card .big{font-size:32px;font-weight:680;letter-spacing:-.02em;}
  .card .lbl{color:var(--mut);font-size:13px;margin-top:4px;}
  .card.accent .big{color:var(--accent)} .card.good .big{color:var(--good)} .card.blue .big{color:var(--blue)} .card.purp .big{color:var(--purp)}
  .chartbox{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:18px 0;}
  canvas{max-height:360px;}
  p{margin:12px 0;} .note{background:#fff;border-left:3px solid var(--accent);padding:12px 16px;border-radius:0 8px 8px 0;color:#444;font-size:15px;margin:14px 0;}
  .key{background:#fbf6ee;border:1px solid var(--line);border-left:3px solid var(--purp);padding:14px 18px;border-radius:0 10px 10px 0;margin:16px 0;}
  table{width:100%;border-collapse:collapse;font-size:14px;margin:12px 0;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;}
  th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top;}
  th{background:#f3efe7;font-weight:620;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:#555;}
  tr:last-child td{border-bottom:none;}
  .q{color:#333;} .g{color:var(--good);font-weight:600;} .b{color:#b34;font-weight:600;}
  .mono{font-variant-numeric:tabular-nums;} code{background:#efeae0;padding:1px 5px;border-radius:4px;font-size:13px;}
  footer{margin-top:48px;color:var(--mut);font-size:13px;border-top:1px solid var(--line);padding-top:16px;}
</style></head>
<body><div class="wrap">
<h1>How small a chunk can Opus 4.8 trace to its author?</h1>
<p class="sub">Open-ended authorship attribution — no tools, no web search, thinking=high, structured JSON output. One independent API call per chunk. Four authors run through the identical pipeline.</p>

<div class="cards" id="cards"></div>

<h2>1. Accuracy vs. chunk length (word count)</h2>
<p>The real independent variable is <b>word count</b> — paragraphs and sentences are pooled into a single curve per author. Below ~10 words there is too little signal to identify anyone; accuracy climbs steeply through 11–35 words and saturates near-ceiling on long passages. All four distinctive authors trace the same S-shape.</p>
<div class="chartbox"><canvas id="lenChart"></canvas></div>

<p>A single clean metric falls out of those curves: <b>how many words it takes to cross 50% and 80% accuracy</b>, estimated by a logistic fit of hit/miss on word count per author. The AI/rationalist-sphere writers are identified ~2–3× faster (per word) than the mainstream columnists.</p>
<table id="thresh"><thead><tr><th>author</th><th>n</th><th>overall</th><th>→ 50% accuracy</th><th>→ 80% accuracy</th></tr></thead><tbody></tbody></table>
<p style="font-size:13px;color:#6b6b6b;">Caveats: Willison's low figure is the noisiest (n=38, and topic-matched to Zvi) — Zvi's 19-word / 33-word figures (n=543) are the most robust. The 80% thresholds for the mainstream writers rest on relatively few long chunks, so carry wider uncertainty than the 50% ones.</p>

<h2>2. The model knows when it knows (calibration)</h2>
<p>Each bar is a confidence band; its height is the <i>actual</i> hit rate of Zvi-chunks the model assigned that confidence. A perfectly calibrated model sits on the dashed diagonal. Opus 4.8 is remarkably well-calibrated: ≥60 confidence is essentially always correct, and it correctly assigns low confidence to the short fragments it gets wrong — its "misses" are mostly it <i>knowing</i> a 4-word scrap is unidentifiable, not overconfident errors.</p>
<div class="chartbox"><canvas id="calibChart"></canvas></div>

<h2>3. Is it recognizing style, the tribe, or just the topic?</h2>
<p>The headline number is only meaningful if the model isn't simply shouting "Zvi" at anything AI-adjacent. Three controls isolate what's really driving attribution. The orange bars are how often each author was correctly identified; the purple bars are how often they were <b>mis-attributed to Zvi</b>.</p>
<div class="chartbox"><canvas id="crossChart"></canvas></div>
<div class="key" id="keybox"></div>
<table id="crosstab"><thead><tr><th>source</th><th>role</th><th>topic</th><th>n</th><th>→ correct</th><th>→ Zvi</th><th>top wrong guesses</th></tr></thead><tbody></tbody></table>

<h2>4. Identifying the other authors</h2>
<p id="douthatpara"></p>
<p>Notably the capability is <b>not</b> Zvi-specific — every distinctive author here is identifiable from a few dozen words, each confused with their own neighbours (Scott Alexander → Yarvin / Žižek / Yudkowsky; Douthat → Yglesias / Krugman / other columnists; Willison → other developer-writers, plus Zvi on shared topic). The model isn't memorizing one author; it's doing genuine stylistic recognition across the board.</p>

<h2>5. Example identifications (Zvi)</h2>
<p>Confident, correct IDs on <b>short</b> chunks (≤15 words):</p>
<table id="hits"><thead><tr><th>chunk</th><th>text</th><th>guess</th><th>conf</th></tr></thead><tbody></tbody></table>
<p>Misses the model was most confident about (the interesting failures):</p>
<table id="misses"><thead><tr><th>chunk</th><th>text</th><th>guess</th><th>conf</th></tr></thead><tbody></tbody></table>

<h2>6. Method &amp; caveats</h2>
<div class="note"><b>What this measures.</b> The target post is genuinely post-cutoff (the model never saw these exact words), but the authors' <i>styles</i> are represented in training. So this tests recognition of distinctive, well-represented authors from small novel samples — not blind stylometry on unknown writers. The same-topic control (Willison) shows topic contributes signal but style dominates; the same-tribe control (Scott) shows there is no lazy "LessWrong → Zvi" shortcut.</div>
<p style="font-size:15px;color:#444;">
• <b>Grading:</b> a hit requires naming the person (e.g. <code>zvi</code>/<code>mowshowitz</code>); blog names and vague categories do not count.<br>
• <b>No tools:</b> zero tools passed — the model cannot search the web for the text. Structured JSON via <code>output_config.format</code>; thinking=high (a sweep showed effort level barely moves results — attribution is a fast judgment, not a reasoning task — so high was chosen purely to preempt any "you sandbagged" objection).<br>
• <b>Independence:</b> every chunk is a separate API call with no shared context, so the model cannot learn to "always say Zvi" within a run.<br>
• <b>Quotes excluded:</b> blockquoted material (tweets, verbatim Anthropic system-card text Zvi quotes, Anthropic's release notes Willison quotes) was stripped before chunking — only each author's own prose is graded.<br>
• <b>Refusals:</b> a few Zvi chunks about biological/chemical threat models triggered content-safety refusals and are excluded.<br>
• <b>Single pass:</b> one call per chunk, so the per-bucket curve carries sampling noise at small n (Willison n=38). Replicates would tighten it.</p>

<footer>zvi-sight · model <code>claude-opus-4-8</code> · open-ended attribution · generated from results*.jsonl</footer>
</div>

<script>
const D = /*DATA*/;
Chart.defaults.font.family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"; Chart.defaults.color="#444";
const COL={zvi:"#c2622d",willison:"#2d6ec2",scott:"#7a4fb5",douthat:"#9a948a",krugman:"#3a8a55",gruber:"#d4a017",levine:"#b5407a",saunders:"#5b8aa0"};
const S=Object.fromEntries(D.sources.map(s=>[s.key,s]));

// cards
document.getElementById("cards").innerHTML = `
  <div class="card accent"><div class="big">${S.zvi.correct}%</div><div class="lbl">Zvi chunks attributed to Zvi (n=${S.zvi.n}); ${S.zvi.curve_long}% on ≥21-word chunks</div></div>
  <div class="card blue"><div class="big">${D.zvi_para}% / ${D.zvi_sent}%</div><div class="lbl">Zvi paragraphs / sentences</div></div>
  <div class="card good"><div class="big">${S.scott.to_zvi}%</div><div class="lbl">Scott Alexander (same tribe) mis-attributed to Zvi — no "LessWrong reflex"</div></div>
  <div class="card purp"><div class="big">${S.willison.to_zvi}%</div><div class="lbl">Willison (same topic) mis-attributed to Zvi — topic adds signal</div></div>`;

const curve=(s)=>D.buckets.map(b=>s.curve[b]?s.curve[b].rate:null);
new Chart(lenChart,{type:"line",data:{labels:D.buckets,datasets:D.sources.map(s=>({
  label:`${s.label}`,data:curve(s),borderColor:COL[s.key],backgroundColor:COL[s.key],
  borderDash:s.key==="douthat"?[5,4]:[],tension:.3,spanGaps:true,pointRadius:3}))},
  options:{scales:{y:{min:0,max:100,title:{display:true,text:"% correctly attributed"}},x:{title:{display:true,text:"chunk length (words)"}}},plugins:{legend:{position:"top"}}}});

const cb=["0–19","20–39","40–59","60–79","80–99"], bands=[0,20,40,60,80];
new Chart(calibChart,{data:{labels:cb,datasets:[
  {type:"bar",label:"actual hit rate",data:bands.map(b=>S.zvi.calib[b]?S.zvi.calib[b].rate:null),backgroundColor:COL.zvi,borderRadius:5},
  {type:"line",label:"perfect calibration",data:[10,30,50,70,90],borderColor:"#999",borderDash:[6,4],pointRadius:0},
]},options:{scales:{y:{min:0,max:100,title:{display:true,text:"actual % correct"}},x:{title:{display:true,text:"model's stated confidence"}}}}});

new Chart(crossChart,{type:"bar",data:{labels:D.sources.map(s=>s.label),datasets:[
  {label:"correctly identified",data:D.sources.map(s=>s.correct),backgroundColor:COL.zvi,borderRadius:5},
  {label:"mis-attributed to Zvi",data:D.sources.map(s=>s.key==="zvi"?null:s.to_zvi),backgroundColor:COL.purp,borderRadius:5},
]},options:{scales:{y:{min:0,max:100,title:{display:true,text:"% of that author's chunks"}}},plugins:{legend:{position:"top"}}}});

document.getElementById("keybox").innerHTML =
  `<b>No tribal shortcut:</b> Scott Alexander — a fellow LessWrong-sphere writer — was identified ${S.scott.correct}% of the time `+
  `(${S.scott.curve_long}% on ≥21-word chunks) and mistaken for Zvi <b>${S.scott.to_zvi}%</b> of the time. The model knows Scott ≠ Zvi.<br>`+
  `<b>Topic is a real but secondary cue:</b> Simon Willison writing about the <i>same</i> subject (Opus 4.8) was mistaken for Zvi <b>${S.willison.to_zvi}%</b> of the time `+
  `(vs 0% for both off-topic controls) — yet still correctly identified as himself ${S.willison.curve_long}% on ≥21-word chunks. Same-topic confusion is real, but style still wins.`;

const ctab=document.querySelector("#crosstab tbody");
ctab.innerHTML=D.sources.map(s=>`<tr><td><b>${s.label}</b></td><td>${s.role}</td><td>${s.topic}</td><td class="mono">${s.n}</td>`+
  `<td class="mono g">${s.correct}%</td><td class="mono ${s.to_zvi>10?'b':''}">${s.key==="zvi"?"—":s.to_zvi+"%"}</td>`+
  `<td style="font-size:13px;color:#666">${s.confusions.map(c=>c[0]+" ("+c[1]+")").join(", ")}</td></tr>`).join("");

const dou=S.douthat;
document.getElementById("douthatpara").innerHTML =
  `<b>Ross Douthat</b> (different author, different topic) is the clean false-positive test, and the model passes it cleanly — `+
  `<b>0%</b> of his column was attributed to Zvi. He's harder to pin than Zvi at equal lengths (${dou.correct}% overall, ${dou.curve_long}% on ≥21-word chunks `+
  `vs Zvi's ${S.zvi.curve_long}%), plausibly because Zvi's voice is more distinctive and more heavily represented in training — but Douthat is still reliably caught on full paragraphs and, like Zvi, the model is well-calibrated about him (high confidence ⇒ correct). When wrong it guesses other opinion columnists (${dou.confusions.slice(0,3).map(c=>c[0]).join(", ")}), never Zvi.`;

function fill(id,rows,hit){document.querySelector(`#${id} tbody`).innerHTML=rows.map(r=>
  `<tr><td class="mono">${r.kind[0]}·${r.words}w</td><td class="q">"${r.text.replace(/</g,"&lt;")}"</td><td class="${hit?'g':'b'}">${r.guess}</td><td class="mono">${r.conf}</td></tr>`).join("");}
fill("hits",D.zvi_hits,true); fill("misses",D.zvi_misses,false);

const tw=(w,ex,mx)=>w==null?'<span style="color:#999">n/a</span>':(w<=1?'<1 word':`${Math.round(w)} words`+(ex?` <span style="color:#b5407a;font-size:12px">(extrap. past ${mx}w)</span>`:''));
document.querySelector("#thresh tbody").innerHTML = D.thresholds.map(r=>{
  const isZvi = r.label.indexOf("Zvi")>=0;
  return `<tr${isZvi?' style="background:#fbf3ec"':''}><td><b>${r.label}</b></td><td class="mono">${r.n}</td><td class="mono">${r.overall}%</td>`+
    `<td class="mono">${tw(r.w50,r.w50_extrap,r.max_words)}</td><td class="mono">${tw(r.w80,r.w80_extrap,r.max_words)}</td></tr>`;
}).join("");
</script>
</body></html>"""


if __name__ == "__main__":
    main()
