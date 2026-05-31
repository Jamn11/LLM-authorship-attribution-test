"""Build a self-contained HTML tool for auditing chunk -> guess -> reasoning.

Browse every attribution call with filters (model, author, correct/wrong,
word-count, free-text search) to inspect *why* the models answer as they do.

  uv run python src/reasoning_browser.py   ->  publish/reasoning_audit.html

NB: embeds verbatim chunk text, so the output is gitignored (local audit tool).
"""
from __future__ import annotations

import json
from pathlib import Path

from grade_report import ALIASES, is_hit
from build_csv import RUNS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ZVI = ALIASES["Zvi Mowshowitz"]
LABELS = {
    "claude-opus-4-8": "Opus 4.8", "claude-opus-4-5": "Opus 4.5",
    "claude-sonnet-4-6": "Sonnet 4.6", "claude-sonnet-4-0": "Sonnet 4.0",
    "openai/gpt-5.5": "GPT-5.5", "deepseek/deepseek-v4-pro": "DeepSeek V4 Pro",
    "deepseek/deepseek-v4-flash": "DeepSeek V4 Flash",
}


def main():
    records = []
    for fname, author, model, provider in RUNS:
        path = DATA / fname
        if not path.exists():
            continue
        aliases = ALIASES[author]
        for line in open(path):
            r = json.loads(line)
            refused = bool(r.get("error"))
            records.append({
                "m": LABELS.get(model, model), "a": author, "k": r.get("kind", ""),
                "w": r.get("n_words", 0), "t": r.get("text", ""),
                "g": "(refused)" if refused else r.get("author_guess", ""),
                "c": "" if refused else r.get("confidence", ""),
                "h": "" if refused else int(is_hit(r.get("author_guess", ""), aliases)),
                "z": "" if refused else int(is_hit(r.get("author_guess", ""), ZVI)),
                "r": r.get("error", "") if refused else r.get("reasoning", ""),
            })
    models = sorted({r["m"] for r in records})
    authors = sorted({r["a"] for r in records})
    html = TEMPLATE.replace("/*DATA*/", json.dumps(records, ensure_ascii=False)) \
                   .replace("/*MODELS*/", json.dumps(models)) \
                   .replace("/*AUTHORS*/", json.dumps(authors))
    out = ROOT / "publish" / "reasoning_audit.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(records)} records, {len(models)} models)")


TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM authorship-attribution test — reasoning audit</title>
<style>
 :root{--ink:#1a1a1a;--mut:#6b6b6b;--line:#e4e0d8;--bg:#faf8f3;--card:#fff;--good:#3a8a55;--bad:#b3344a;}
 *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;}
 header{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--line);padding:14px 20px;z-index:5;}
 h1{font-size:18px;margin:0 0 10px;}
 .ctl{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;font-size:13px;}
 .ctl label{color:var(--mut);margin-right:4px;}
 select,input{font:13px inherit;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:#fff;}
 input[type=number]{width:64px;} input[type=search]{width:240px;}
 .count{margin-left:auto;color:var(--mut);font-variant-numeric:tabular-nums;}
 main{padding:8px 20px 60px;}
 .row{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:8px;padding:10px 14px;margin:8px 0;}
 .row.hit{border-left-color:var(--good);} .row.miss{border-left-color:var(--bad);}
 .meta{font-size:12px;color:var(--mut);display:flex;flex-wrap:wrap;gap:4px 12px;margin-bottom:5px;}
 .meta b{color:var(--ink);} .g-hit{color:var(--good);font-weight:600;} .g-miss{color:var(--bad);font-weight:600;}
 .txt{margin:3px 0;} .why{margin:5px 0 0;color:#444;font-size:13px;border-top:1px dashed var(--line);padding-top:5px;}
 .why::before{content:"why: ";color:var(--mut);}
 .pill{background:#f0ece2;border-radius:10px;padding:1px 7px;font-size:11px;}
 mark{background:#ffe6a8;}
</style></head><body>
<header>
 <h1>LLM authorship-attribution test — chunk → guess → reasoning audit</h1>
 <div class="ctl">
  <span><label>model</label><select id="fm"></select></span>
  <span><label>true author</label><select id="fa"></select></span>
  <span><label>result</label><select id="fh"><option value="">all</option><option value="1">correct</option><option value="0">wrong</option><option value="z">→Zvi only</option></select></span>
  <span><label>words</label><input type="number" id="fwmin" placeholder="min"> – <input type="number" id="fwmax" placeholder="max"></span>
  <span><label>conf≥</label><input type="number" id="fc" placeholder="0" style="width:54px"></span>
  <span><input type="search" id="fq" placeholder="search text / guess / reasoning"></span>
  <span class="count" id="count"></span>
 </div>
</header>
<main id="list"></main>
<script>
const D=/*DATA*/, MODELS=/*MODELS*/, AUTHORS=/*AUTHORS*/;
const $=id=>document.getElementById(id);
function opts(sel,arr){sel.innerHTML='<option value="">all</option>'+arr.map(x=>`<option>${x}</option>`).join("");}
opts($("fm"),MODELS); opts($("fa"),AUTHORS);
const esc=s=>(s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
function hl(s,q){s=esc(s); if(!q)return s; try{return s.replace(new RegExp("("+q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+")","ig"),"<mark>$1</mark>");}catch(e){return s;}}
function render(){
 const m=$("fm").value,a=$("fa").value,h=$("fh").value,q=$("fq").value.trim(),
  wmin=+$("fwmin").value||0,wmax=+$("fwmax").value||1e9,cmin=+$("fc").value||0;
 const ql=q.toLowerCase();
 let out=[],n=0;
 for(const d of D){
  if(m&&d.m!==m)continue; if(a&&d.a!==a)continue;
  if(h==="1"&&d.h!==1)continue; if(h==="0"&&d.h!==0)continue; if(h==="z"&&d.z!==1)continue;
  if(d.w<wmin||d.w>wmax)continue; if(d.c!==""&&d.c<cmin)continue; if(d.c===""&&cmin>0)continue;
  if(q&&!((d.t+" "+d.g+" "+d.r).toLowerCase().includes(ql)))continue;
  n++; if(out.length>=600)continue;
  const cls=d.h===1?"hit":(d.h===0?"miss":"");
  const gcls=d.h===1?"g-hit":(d.h===0?"g-miss":"");
  out.push(`<div class="row ${cls}"><div class="meta"><span class="pill">${d.m}</span>`+
   `<span>true: <b>${d.a}</b></span><span>${d.k} · ${d.w}w</span>`+
   (d.c!==""?`<span>conf <b>${d.c}</b></span>`:"")+
   `<span>guess: <span class="${gcls}">${esc(d.g)}</span></span></div>`+
   `<div class="txt">"${hl(d.t,q)}"</div>`+(d.r?`<div class="why">${hl(d.r,q)}</div>`:"")+`</div>`);
 }
 $("count").textContent=`${n} match${n===1?"":"es"}`+(n>600?" (showing first 600)":"");
 $("list").innerHTML=out.join("")||'<p style="color:#888">no matches</p>';
}
["fm","fa","fh","fwmin","fwmax","fc","fq"].forEach(id=>{$(id).addEventListener("input",render);});
render();
</script></body></html>"""


if __name__ == "__main__":
    main()
