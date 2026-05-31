# LLM authorship-attribution test: how few words does a frontier model need to identify an author?

A small empirical study of **authorship attribution by large language models**. We
ask a model, with no tools and no web access, *"who wrote this?"* for every
paragraph and every sentence of a set of recent (post-training-cutoff) articles,
and measure how accuracy scales with chunk length — and whether the model is
recognizing **style**, the author's **intellectual tribe**, or merely the **topic**.

## TL;DR findings

- Attribution accuracy is a steep function of **word count**. For Zvi Mowshowitz,
  Claude Opus 4.8 crosses 50% accuracy at ~18 words and 80% at ~34 words.
- Frontier models are **well-calibrated** — Opus 4.8 / GPT-5.5 / Sonnet 4.6 are
  96–100% correct when they report ≥60% confidence, and abstain on fragments too
  short to identify.
- It is **not a tribe heuristic**: a fellow LessWrong-sphere writer (Scott
  Alexander) was *never* misattributed to Zvi.
- **Topic is a real but secondary cue**: the only author ever mistaken for Zvi was
  Simon Willison writing about the *same* subject (Claude Opus 4.8) — and even he
  was correctly identified most of the time.
- **Open-weights models trail badly**: DeepSeek V4 Pro reaches only 20% on
  ≥21-word chunks (Flash: 2%) vs. 81–84% for Opus 4.8 / GPT-5.5, and is
  *confidently wrong*. Capability improved sharply across model generations.

See [`SUMMARY.md`](SUMMARY.md) for the full writeup, tables, and figures.

## What's here

```
publish/
  README.md            this file
  SUMMARY.md           the writeup: findings, tables, figures
  data/
    attributions.csv   one row per (chunk, model) attribution call  ← the dataset
  figures/             static charts used in the summary
```

> **Note on source text.** The public dataset ships **without** the verbatim
> article text (`--strip-text`); it contains only per-chunk *metadata and model
> outputs*, which are facts/measurements rather than the authors' expression. The
> original articles can be re-fetched from their URLs with the scraper in the
> companion code. (A full-text version exists only where the author has given
> permission.)

## Data dictionary — `data/attributions.csv`

One row per attribution call (one model judging one chunk).

| column | meaning |
|---|---|
| `true_author` | who actually wrote the chunk |
| `provider` | `anthropic` or `openrouter` |
| `model` | model id (e.g. `claude-opus-4-8`, `claude-opus-4-5`, `openai/gpt-5.5`) |
| `thinking` | reasoning/effort level used (`none`/`low`/`medium`/`high`/`xhigh`) |
| `chunk_id` | stable id; `pN` = paragraph N, `pNsM` = sentence M of paragraph N |
| `kind` | `paragraph` or `sentence` |
| `n_words` | word count of the chunk |
| `paragraph_id` | source paragraph index (lets you group sentences by paragraph) |
| `trial` | repeat index (0 unless replicates were run) |
| `guess` | the model's free-text author guess |
| `confidence` | model's stated confidence, 0–100 |
| `is_specific_person` | model flagged the guess as a specific named individual |
| `hit` | 1 if `guess` names `true_author` (precise-name match), else 0 |
| `attributed_to_zvi` | 1 if `guess` names Zvi Mowshowitz (false-positive probe) |
| `refused` | 1 if the model refused / returned no answer (content safety) |
| `input_tokens` / `output_tokens` | token usage for the call |
| `cost_usd` | call cost (provider-reported for OpenRouter; computed from list prices for Anthropic) |
| `reasoning` | the model's own one–two-sentence rationale for the guess |
| `text` | verbatim chunk text (present only in the permissioned full version) |

## Method (summary)

- **Open-ended** attribution: the model gets a neutral *"who wrote this?"* prompt
  and returns a named guess + confidence via structured JSON. No multiple-choice,
  no candidate list.
- **No tools / no web search** are ever passed to the model, so it cannot look up
  the text — it relies only on its own knowledge of style and content.
- **Independence**: every chunk is a separate API call with no shared context, so
  the model cannot "learn to always say X" within a run.
- **Quotes excluded**: blockquoted material (tweets, verbatim system-card text,
  press-release quotes) is stripped before chunking — only each author's own prose
  is graded.
- **Grading** is a precise-name alias match; vague categories and blog names do
  not count as hits.

## Caveats

- The target articles are post-training-cutoff (novel text), but the authors'
  *styles* are represented in training — this tests recognition of distinctive,
  well-represented authors, not blind stylometry on unknown writers.
- Single pass per chunk (no replicates yet), so small-n authors carry sampling
  noise.
- Cross-model thinking settings are each model's strongest readily-available
  config; a thinking-level sweep showed this knob is near-inert for this task.
