# Agent instructions — calculating the numbers for one article

This is a step-by-step runbook for an autonomous agent (or a human) to take a
single article and produce the attribution numbers for it: overall hit rate, the
accuracy-vs-length curve, calibration, the confusion list, and the headline
**words-to-50% / words-to-80%** thresholds.

The pipeline is four scripts run in order:

```
scrape.py  →  run_attribution.py  →  grade_report.py  →  thresholds.py
 (chunks)        (model guesses)        (the report)      (word thresholds)
```

Every script is a plain CLI. Nothing here needs the prebuilt `publish/` bundle —
that is just the curated output of a previous multi-article run.

---

## 0. One-time setup

```bash
uv sync                      # install deps into .venv (Python >=3.14)
cp .env.example .env         # then edit .env and paste your real keys
```

`.env` must contain at least:

```
ANTHROPIC_API_KEY=sk-ant-...           # required for Claude models
OPENROUTER_API_KEY=sk-or-v1-...        # only needed for --provider openrouter (GPT, DeepSeek, ...)
```

`.env` is gitignored — never commit real keys. All commands below are run from
the repo root and prefixed with `uv run python` so they use the synced env.

Working files land in `data/` (gitignored). Pick a short slug for the author
(e.g. `willison`) and use it consistently in the filenames below.

---

## 1. Scrape the article into chunks

`scrape.py` fetches the article, strips blockquotes (so only the author's own
prose is graded), and splits it into **paragraph** chunks and **sentence**
chunks, writing one JSON file.

From a URL (Substack/blog layouts are auto-detected):

```bash
uv run python src/scrape.py \
  --url "https://example.com/the-article" \
  --author "Simon Willison" \
  --out data/chunks_willison.json
```

From pasted text instead (use this for paywalled sources you can't fetch):

```bash
uv run python src/scrape.py \
  --text-file data/willison.txt \
  --author "Simon Willison" \
  --title "Optional article title" \
  --out data/chunks_willison.json
```

Useful flags:
- `--container "<css-selector>"` — if auto-detection grabs the wrong region on a
  non-Substack site, pass the article body's CSS selector.
- `--refetch` — bypass the cached raw HTML and re-download.
- `--min-para-words N` / `--min-sent-words N` — drop chunks shorter than N words
  (defaults: 5 for paragraphs, 1 for sentences).

`--author` is just metadata recorded in the chunks file; the real grading key is
set in step 3/4. Use the author's canonical full name.

---

## 2. Run the model over the chunks

`run_attribution.py` asks the model *"who wrote this?"* once per chunk — **no
tools, no web search**, structured JSON output, each call independent. Output is
one JSON line per chunk.

**Convention that matters:** name the output `data/results_<slug>.jsonl`.
`thresholds.py` looks for results by a fixed filename per author (see step 4).
The target author Zvi uses the bare `data/results.jsonl`.

```bash
# Claude (Anthropic), the default provider, thinking=high:
uv run python src/run_attribution.py \
  --model claude-opus-4-8 \
  --chunks data/chunks_willison.json \
  --out data/results_willison.jsonl

# A model via OpenRouter (GPT, DeepSeek, ...):
uv run python src/run_attribution.py \
  --provider openrouter \
  --model openai/gpt-5.5 \
  --thinking medium \
  --chunks data/chunks_willison.json \
  --out data/results_gpt55.jsonl
```

Useful flags:
- `--kind paragraph|sentence|both` — which chunk types to run (default `both`).
- `--thinking none|low|medium|high|xhigh` — reasoning effort (default `high`; a
  sweep found this knob near-inert for this task, so keep `high` for
  defensibility).
- `--workers N` — concurrency (default 32). Raise/lower to fit rate limits.
- `--trials N` — repeat each chunk N times for replicates (default 1).
- `--limit N` — only run the first N chunks (quick smoke test).
- `--resume` — skip chunks already present in the `--out` file; safe to re-run
  after an interruption or a rate-limit stop.

This is the only step that costs money / hits an API.

---

## 3. Grade and print the report

`grade_report.py` scores each guess against the true author and prints the
report: hit rate (overall, by paragraph/sentence, and by word-count bucket),
calibration (stated confidence vs. actual hit rate), and the top wrong guesses.

```bash
uv run python src/grade_report.py \
  --results data/results_willison.jsonl \
  --author "Simon Willison" \
  --show-misses 10        # optional: also dump the 10 longest missed chunks
```

Grading is a **transparent alias match** (no LLM judge): a guess counts as a hit
if it contains any of the true author's aliases. Aliases live in the `ALIASES`
dict at the top of `src/grade_report.py`:

```python
ALIASES = {
    "Zvi Mowshowitz": ["zvi", "mowshowitz"],
    "Simon Willison": ["simon willison", "willison"],
    ...
}
```

> **If the article is by an author not already in `ALIASES`, add an entry first.**
> Key = the exact string you pass to `--author`; value = lowercase precise-name
> fragments (surname, full name). Keep blog names out so a hit means the model
> named the *person*. If you skip this, `grade_report.py` falls back to matching
> the normalized name, but `thresholds.py` (step 4) will **KeyError** — so always
> add the alias.

---

## 4. Compute the words-to-50% / words-to-80% thresholds

`thresholds.py` fits a 1-D logistic regression of hit/miss on chunk word count
and reports the word count at which accuracy crosses 50% and 80% — the headline
number of the whole experiment.

```bash
uv run python src/thresholds.py
```

It prints a table over **all** authors whose results files exist. It discovers
results by a hardcoded `(label, filename, author)` map — the `SOURCES` list at
the top of `src/thresholds.py`:

```python
SOURCES = [
    ("Zvi Mowshowitz", "results.jsonl",            "Zvi Mowshowitz"),
    ("Simon Willison", "results_willison.jsonl",   "Simon Willison"),
    ...
]
```

> **To add a new article/author**, add one row to `SOURCES` whose filename
> matches the `--out` you used in step 2, and whose author string matches an
> `ALIASES` key from step 3. Authors whose results file is absent are silently
> skipped, so you can keep all rows in place.

Thresholds that fall beyond the longest chunk actually present for that author
are flagged `(extrapolated)` — treat those as projections, not observations.

---

## 5. (Optional) Regenerate the full publishable bundle

Once result files for the authors/models you care about exist in `data/`,
regenerate every CSV, figure, and the interactive HTML report — **no API calls,
no cost**:

```bash
uv run python main.py
```

This writes the consolidated CSV (with and without verbatim text), the static
figures, the comparison tables, and `publish/report.html`. The text-stripped
`publish/data/attributions_public.csv` is the shareable dataset; the full-text
CSV and `publish/reasoning_audit.html` are gitignored because they embed
copyrighted article text.

---

## Quick reference — minimum path for one new article

```bash
# 0. setup once
uv sync && cp .env.example .env   # then paste real keys into .env

# 1. scrape
uv run python src/scrape.py --url "<URL>" --author "<Full Name>" \
  --out data/chunks_<slug>.json

# 2. run the model  (costs money)
uv run python src/run_attribution.py --model claude-opus-4-8 \
  --chunks data/chunks_<slug>.json --out data/results_<slug>.jsonl

# 3. (first time for this author) add the name to ALIASES in src/grade_report.py
#    and add a SOURCES row in src/thresholds.py pointing at results_<slug>.jsonl

# 4. read the numbers
uv run python src/grade_report.py --results data/results_<slug>.jsonl --author "<Full Name>"
uv run python src/thresholds.py
```
