"""Ask a model to attribute authorship of each chunk -- open-ended, no tools.

Backends:
  --provider anthropic   (default)  Claude models, structured output via output_config.format
  --provider openrouter             OpenAI-compatible (e.g. openai/gpt-5.5), response_format json_schema

Critical design choices (both backends):
  * NO tools / function-calling beyond the structured-output schema -> the model
    cannot search the web for the text. It relies only on its own knowledge.
  * Neutral prompt: never mentions Zvi, Substack, blogs, or AI writers.
  * One call per (chunk, trial); calls are independent and run concurrently,
    so there is no cross-chunk contamination.

Thinking / reasoning effort (--thinking): none | low | medium | high | xhigh
  Anthropic 4.6/4.7/4.8: adaptive thinking + output_config.effort (none -> disabled)
  Anthropic 4.5:         extended thinking (budget_tokens) when on; 4.5 lacks adaptive
  Anthropic <=4.1:       extended thinking (budget_tokens) when on
  OpenRouter (OpenAI):   reasoning.effort (xhigh->high, none->minimal)

Reads:  data/chunks.json     Writes: <--out> jsonl, one line per (chunk, trial)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from anthropic import Anthropic
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
DATA = ROOT / "data"
MODEL = "claude-opus-4-8"
THINKING_LEVELS = ["none", "low", "medium", "high", "xhigh"]
ADAPTIVE_MODELS = {"claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6"}
# Models that support output_config.format (structured outputs). Older models
# (Sonnet 4.0, Opus 4.0) do not -> fall back to forced tool use.
STRUCTURED_OUTPUT_MODELS = {
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-opus-4-5",
    "claude-opus-4-1", "claude-sonnet-4-6", "claude-haiku-4-5",
}
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SYSTEM = (
    "You are an expert in authorship attribution and stylometry. You will be "
    "shown a short excerpt of writing and must identify who most likely wrote it. "
    "The excerpt may come from something published very recently, possibly after "
    "your training cutoff, so reason from writing style, voice, vocabulary, and "
    "subject matter rather than from having seen this exact text. Always commit to "
    "a single best guess of a specific, named person, even when you are unsure; "
    "use the confidence score to express how certain you are."
)
USER_TEMPLATE = (
    "Who wrote the following excerpt? Name the specific person you think is the "
    "most likely author.\n\n<excerpt>\n{excerpt}\n</excerpt>"
)
SCHEMA = {
    "type": "object",
    "properties": {
        "author_guess": {"type": "string", "description": "Single best guess at the specific author's full name."},
        "is_specific_person": {"type": "boolean", "description": "True if the guess names a specific real individual, not a vague category."},
        "confidence": {"type": "integer", "description": "0-100 confidence that the named author is correct."},
        "reasoning": {"type": "string", "description": "One or two sentences on the cues (style, content) behind the guess."},
    },
    "required": ["author_guess", "is_specific_person", "confidence", "reasoning"],
    "additionalProperties": False,
}

_print_lock = threading.Lock()


# ---------- Anthropic backend ----------

def anthropic_kwargs(model: str, excerpt: str, thinking: str) -> dict:
    oc = {"format": {"type": "json_schema", "schema": SCHEMA}}
    kw = dict(model=model, max_tokens=16000, system=SYSTEM,
              messages=[{"role": "user", "content": USER_TEMPLATE.format(excerpt=excerpt)}],
              output_config=oc)
    if model in ADAPTIVE_MODELS:
        if thinking == "none":
            kw["thinking"] = {"type": "disabled"}
        else:
            kw["thinking"] = {"type": "adaptive"}
            oc["effort"] = thinking
    else:  # Opus 4.5 / 4.1 / 4.0: no adaptive thinking. Use extended thinking when "on".
        if thinking != "none":
            kw["thinking"] = {"type": "enabled", "budget_tokens": 8000}
    return kw


# Forced-tool fallback for models without output_config.format. Forcing a tool
# is incompatible with thinking, so these run no-thinking (the thinking sweep
# showed the knob is near-inert for this task anyway).
ATTR_TOOL = {"name": "submit_attribution",
             "description": "Submit your authorship attribution for the excerpt.",
             "input_schema": SCHEMA}


def call_anthropic(client: Anthropic, model: str, excerpt: str, thinking: str) -> dict:
    if model in STRUCTURED_OUTPUT_MODELS:
        resp = client.messages.create(**anthropic_kwargs(model, excerpt, thinking))
        text = next((b.text for b in resp.content if b.type == "text"), None)
        if text is None:
            return {"error": f"no text block (stop_reason={resp.stop_reason})"}
        out = json.loads(text)
    else:
        resp = client.messages.create(
            model=model, max_tokens=1024, system=SYSTEM,
            messages=[{"role": "user", "content": USER_TEMPLATE.format(excerpt=excerpt)}],
            tools=[ATTR_TOOL], tool_choice={"type": "tool", "name": "submit_attribution"})
        blk = next((b for b in resp.content if b.type == "tool_use" and b.name == "submit_attribution"), None)
        if blk is None:
            return {"error": f"no tool_use (stop_reason={resp.stop_reason})"}
        out = dict(blk.input)
    out["_usage"] = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
    return out


# ---------- OpenRouter backend ----------

def openrouter_effort(thinking: str) -> str | None:
    return {"none": "minimal", "xhigh": "high"}.get(thinking, None if thinking == "none" else thinking)


# Some OpenRouter providers (e.g. DeepSeek) don't support json_schema response
# format -> fall back to json_object mode + an explicit field spec in the prompt.
JSON_OBJECT_MODELS = ("deepseek",)
JSON_FIELDS_INSTRUCTION = (
    "\n\nRespond ONLY with a JSON object with exactly these keys: "
    '"author_guess" (string, the specific person), "is_specific_person" (boolean), '
    '"confidence" (integer 0-100), "reasoning" (string, one or two sentences).'
)


def call_openrouter(api_key: str, model: str, excerpt: str, thinking: str) -> dict:
    json_object = any(k in model.lower() for k in JSON_OBJECT_MODELS)
    user = USER_TEMPLATE.format(excerpt=excerpt) + (JSON_FIELDS_INSTRUCTION if json_object else "")
    body = {
        "model": model,
        "max_tokens": 8000,  # bounds OpenRouter's upfront credit reservation; covers reasoning + the small JSON answer
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
    }
    if json_object:
        body["response_format"] = {"type": "json_object"}
    else:
        body["response_format"] = {"type": "json_schema",
                                   "json_schema": {"name": "attribution", "strict": True, "schema": SCHEMA}}
    if thinking != "none":
        body["reasoning"] = {"effort": openrouter_effort(thinking)}
    r = requests.post(OPENROUTER_URL,
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=300)
    j = r.json()
    if "error" in j:
        return {"error": f"openrouter: {j['error'].get('message', j['error'])}"}
    content = j["choices"][0]["message"]["content"]
    out = json.loads(content)
    # json_object mode isn't schema-validated -> coerce/fill defensively
    out = {"author_guess": str(out.get("author_guess", "")).strip(),
           "is_specific_person": bool(out.get("is_specific_person", True)),
           "confidence": int(out.get("confidence", 0) or 0),
           "reasoning": str(out.get("reasoning", ""))}
    u = j.get("usage", {})
    out["_usage"] = {"in": u.get("prompt_tokens", 0), "out": u.get("completion_tokens", 0)}
    out["_cost"] = u.get("cost")
    return out


# ---------- dispatch + retry ----------

def attribute_once(excerpt: str, thinking: str = "high", provider: str = "anthropic",
                   model: str = MODEL, client=None, max_retries: int = 5) -> dict:
    for attempt in range(max_retries):
        try:
            if provider == "anthropic":
                return call_anthropic(client, model, excerpt, thinking)
            return call_openrouter(client, model, excerpt, thinking)
        except Exception as e:  # noqa: BLE001 - rate limits / transient / json errors
            if attempt == max_retries - 1:
                return {"error": f"{type(e).__name__}: {e}"}
            time.sleep(2 ** attempt + 0.5)
    return {"error": "exhausted retries"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["anthropic", "openrouter"], default="anthropic")
    ap.add_argument("--model", default=MODEL, help="e.g. claude-opus-4-5, openai/gpt-5.5")
    ap.add_argument("--chunks", default=str(DATA / "chunks.json"))
    ap.add_argument("--out", default=str(DATA / "results.jsonl"))
    ap.add_argument("--kind", choices=["paragraph", "sentence", "both"], default="both")
    ap.add_argument("--thinking", choices=THINKING_LEVELS, default="high")
    ap.add_argument("--trials", type=int, default=1)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    if args.provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY not set (.env).")
        client = Anthropic()
    else:
        client = os.environ.get("OPENROUTER_API_KEY")
        if not client:
            sys.exit("OPENROUTER_API_KEY not set (.env).")

    data = json.load(open(args.chunks))
    chunks = data["chunks"]
    if args.kind != "both":
        chunks = [c for c in chunks if c["kind"] == args.kind]
    if args.limit:
        chunks = chunks[: args.limit]

    done = set()
    if args.resume and Path(args.out).exists():
        # Keep only SUCCESSFUL records as "done"; drop errored lines so they get retried.
        kept = []
        for line in open(args.out):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("error"):
                done.add((r["id"], r["trial"]))
                kept.append(line if line.endswith("\n") else line + "\n")
        with open(args.out, "w", encoding="utf-8") as f:
            f.writelines(kept)
        print(f"resume: kept {len(done)} successful results; errored/missing will be retried")

    jobs = [(c, t) for c in chunks for t in range(args.trials) if (c["id"], t) not in done]
    print(f"provider={args.provider} model={args.model} thinking={args.thinking} "
          f"chunks={len(chunks)} jobs={len(jobs)} workers={args.workers}")
    if not jobs:
        print("nothing to do."); return

    out_f = open(args.out, "a", encoding="utf-8")
    counters = {"done": 0, "err": 0, "in_tok": 0, "out_tok": 0, "cost": 0.0}
    t0 = time.time()

    def work(job):
        chunk, trial = job
        return chunk, trial, attribute_once(chunk["text"], args.thinking, args.provider, args.model, client)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, j) for j in jobs]
        for fut in as_completed(futs):
            chunk, trial, res = fut.result()
            rec = {"id": chunk["id"], "kind": chunk["kind"], "n_words": chunk["n_words"],
                   "paragraph_id": chunk["paragraph_id"], "trial": trial,
                   "provider": args.provider, "model": args.model, "thinking": args.thinking,
                   "text": chunk["text"], **res}
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n"); out_f.flush()
            counters["done"] += 1
            if "error" in res:
                counters["err"] += 1
            else:
                u = res.get("_usage", {}); counters["in_tok"] += u.get("in", 0); counters["out_tok"] += u.get("out", 0)
                if res.get("_cost"):
                    counters["cost"] += res["_cost"]
            if counters["done"] % 20 == 0 or counters["done"] == len(jobs):
                with _print_lock:
                    extra = f" cost=${counters['cost']:.2f}" if counters["cost"] else ""
                    print(f"  {counters['done']}/{len(jobs)} err={counters['err']} "
                          f"{counters['done']/max(time.time()-t0,1e-6):.1f}/s tok={counters['in_tok']}/{counters['out_tok']}{extra}")
    out_f.close()
    print(f"\nwrote {args.out}  errors={counters['err']}  tok in/out={counters['in_tok']}/{counters['out_tok']}"
          + (f"  cost=${counters['cost']:.2f}" if counters["cost"] else ""))


if __name__ == "__main__":
    main()
