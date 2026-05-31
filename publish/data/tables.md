# zvi-sight — comparison tables

_Threshold estimates from logistic fits; brackets are 90% bootstrap CIs (200 resamples)._

### Table 2 — Cross-model on the Zvi post

| model | released | chunks | overall | ≥21w | →50% (90% CI) | →80% | in tok | out tok | cost | $/correct |
|---|---|---|---|---|---|---|---|---|---|---|
| Opus 4.8 | 2026-05-28 | 450 | 59% | 81% | 18w [16–21] | 34w | 275,348 | 52,751 | $2.70 | $0.010 |
| GPT-5.5 | 2026-04-23 | 454 | 61% | 84% | 18w [16–19] | 29w | 123,728 | 378,820 | $11.98 | $0.043 |
| DeepSeek V4 Pro | 2026-04-23 | 454 | 13% | 20% | 80w [65–101] | 116w | 107,110 | 504,534 | $0.46 | $0.008 |
| DeepSeek V4 Flash | 2026-04-23 | 454 | 1% | 2% | 145w [113–299] | 181w | 107,110 | 193,083 | $0.06 | $0.010 |
| Sonnet 4.6 | 2026-02-17 | 451 | 40% | 62% | 31w [28–34] | 49w | 211,873 | 253,907 | $4.44 | $0.025 |
| Opus 4.5 | 2025-11-24 | 454 | 45% | 65% | 28w [26–30] | 45w | 226,520 | 271,282 | $7.91 | $0.039 |
| Sonnet 4.0 | 2025-05-22 | 454 | 8% | 15% | 73w [64–87] | 95w | 307,332 | 63,569 | $1.88 | $0.049 |

### Table 1 — Opus 4.8, accuracy thresholds by author

| author | work | chunks | words→50% (90% CI) | words→80% (90% CI) |
|---|---|---|---|---|
| Zvi Mowshowitz | Claude Opus 4.8: The System Card | 450 | 18w [17–20] | 34w [30–37] |
| Simon Willison | Claude Opus 4.8 | 38 | 17w [13–21] | 26w [20–35] |
| Scott Alexander | Book Review: The Dialectical Imag… | 373 | 25w [22–28] | 44w [39–52] |
| Paul Krugman | Europe Versus America: A Response… | 109 | 52w [38–75] | 102w [69–161] |
| John Gruber | What Is a Dickover? | 77 | 94w [59–148] | 157w [103–258] |
| Ross Douthat | The Best News in America | 49 | 60w [48–74] | 81w [61–106] |

### Table 3 — Style vs. tribe vs. topic (Opus 4.8)

| author | role | topic | correct | → Zvi | top wrong guesses |
|---|---|---|---|---|---|
| Zvi Mowshowitz | target | AI / Opus 4.8 | 59% | — | Scott Alexander, Eliezer Yudkowsky, Andrej Karpathy |
| Simon Willison | same-topic | AI / Opus 4.8 | 53% | 21% | Zvi Mowshowitz, Linus Torvalds, John Smith |
| Scott Alexander | same-tribe | book review | 51% | 0% | Curtis Yarvin, Slavoj Žižek, Eliezer Yudkowsky |
| Paul Krugman | control | economics | 38% | 0% | Noah Smith, Tyler Cowen, Scott Alexander |
| John Gruber | control | tech | 22% | 0% | Cory Doctorow, Scott Alexander, Maciej Cegłowski |
| Ross Douthat | control | politics | 22% | 0% | Matthew Yglesias, Paul Krugman, Jeff Asher |
