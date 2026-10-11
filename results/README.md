# Results

Every test run, numbered like the iterations table in the write-up. Nothing edited.

| Folder | Step | Model, prompt | Tests x runs | Passed (all checks) |
|---|---|---|---|---|
| `1-sonnet-21x1` | First build | Sonnet 5.5, v1 | 21 x1 | 57% as scored, 100% by hand |
| `2-haiku-21x1` | Cheaper model | Haiku 5.5, v1 | 21 x1 | 86% as scored, 100% by hand |
| `3-haiku-28x3` | 7 harder tests, 3 runs each | Haiku 5.5, v1 | 28 x3 | 92% / 96% |
| `4-haiku-37x3` | 9 complex tests | Haiku 5.5, v1 | 37 x3 | 95% / 98% |
| `5-haiku-43x3-baseline` | 6 tests in French, Spanish, Arabic | Haiku 5.5, v1 | 43 x3 | 96% / 95% |
| `5-.../regraded-with-quality-checks` | Step 6: same answers, re-scored with the answer-quality checks. **This is the baseline.** | Haiku 5.5, v1 | 43 x3 | 13% |
| `7-variation1-haiku-prompt-v2` | Variation 1: better answer instructions. **Final version.** | Haiku 5.5, v2 | 43 x3 | 81% |
| `8-variation2-sonnet` | Variation 2: bigger model | Sonnet 5.5, v1 | 43 x3 | 15% |

"As scored" = what the grader said. "By hand" = after rereading every failed answer to see if the agent or the grader was wrong. The bar got stricter at step 6 (answer quality), so steps 1-5 and 6-8 are not comparable.

## Files in each folder
- `summary.csv`: one line per metric, with its target.
- `results.csv`: one line per answer: the request, what the agent did, each check (pass/fail), the answer text, cost and time.
- `transcripts.jsonl`: the full conversation for each answer, including every tool call and result.
- `*_regraded*` / `regraded-with-quality-checks/`: the same answers, scored again by a newer grader (no new AI calls).
