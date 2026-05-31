# LLM authorship-attribution test

**How few words does a frontier LLM need to identify an author?**

An empirical study of open-ended authorship attribution: show a model a chunk of
text (a paragraph, or a single sentence) and ask — with no tools and no web access —
*"who wrote this?"* Measure how accuracy scales with chunk length, how well the
model knows when it's right, and whether it's recognizing **style**, the author's
**tribe**, or just the **topic**. Run across seven models (Opus 4.8/4.5, Sonnet
4.6/4.0, GPT-5.5, DeepSeek V4 Pro/Flash) and six authors.

➡️ **Findings & charts: [`publish/SUMMARY.md`](publish/SUMMARY.md).**
➡️ **Dataset & data dictionary: [`publish/README.md`](publish/README.md).**

## Repo layout

```
src/                 the pipeline
  scrape.py          fetch an article (or ingest pasted text) -> paragraph/sentence chunks
                     (excludes blockquotes so only the author's own prose is graded)
  run_attribution.py ask a model "who wrote this?" per chunk (Anthropic + OpenRouter
                     backends; no tools; structured JSON output)
  grade_report.py    precise-name grading + a terminal report
  thresholds.py      logistic fit -> words-to-50% / words-to-80% per author/model
  thinking_sweep.py  compares reasoning-effort levels (found near-inert for this task)
  build_csv.py       consolidate all runs -> one tidy CSV (--strip-text for public)
  charts.py          core static figures
  artifacts.py       comparison tables (+ bootstrap CIs), over-time graph, per-pairing curves
  report_html.py     interactive HTML report (Chart.js)
publish/             the curated, shareable bundle (figures, tables, writeup, public CSV)
data/                local working state -- raw HTML, chunks, raw results (gitignored)
main.py              regenerate all artifacts from existing run data (no API calls)
```

## Reproduce

See [`agent-instructions.md`](agent-instructions.md) for a precise, step-by-step
runbook (including how to add a new author). The short version:

```bash
uv sync                                   # install deps
# create .env with ANTHROPIC_API_KEY (and OPENROUTER_API_KEY for GPT models)

# 1. build a dataset from an article (Substack/blog auto-detected; --container for other sites)
uv run python src/scrape.py --url <article-url> --author "Name" --out data/chunks.json
#    or ingest pasted text (for paywalled sources):
uv run python src/scrape.py --text-file data/piece.txt --author "Name" --out data/chunks.json

# 2. run a model over the chunks (no tools / no web search are ever passed)
uv run python src/run_attribution.py --model claude-opus-4-8 --out data/results.jsonl
uv run python src/run_attribution.py --provider openrouter --model openai/gpt-5.5 \
    --thinking medium --out data/results_gpt55.jsonl

# 3. regenerate every table, figure, and the report from the run data (no API cost)
uv run python main.py
```

## Method notes

- **No tools / no web search** are ever passed to the attributed model — it cannot
  look up the text. Structured output via `output_config.format` (Anthropic) /
  `response_format` json_schema (OpenRouter); a forced-tool fallback covers older
  models without structured-output support.
- Each chunk is an **independent** call (no shared context), so a model can't learn
  to "always say X" within a run.
- **Quotes are excluded** before chunking; grading is a strict precise-name match.
- The target articles are post-training-cutoff (novel text). See `publish/SUMMARY.md`
  for the full caveats.

*Preliminary, single-pass results — see the open questions in the summary.*
