# AI71 case: travel agent

A travel assistant for a digital bank. It reads a trip request, looks at the
customer's card payments for travel habits, searches fake flights and hotels,
and proposes one trip within budget. It never books.

**Final version:** Haiku 5.5 + prompt v2. On 43 tests run 3 times each, 81% of answers pass every check (baseline: 13%), at $0.0016 per request. Every run is in `results/` (see `results/README.md`).

## Files
| File | What it is |
|---|---|
| `data/build_data.py` | Builds the fake world (flights, hotels, 8 test customers). Fixed seed: same world every time. |
| `data/*.json` | The fake world itself. |
| `check_data.py` | Checks that every test's trap is really in the data. |
| `world.py` | Loads the data, recomputes trip prices. Shared by the agent and the grader. |
| `tools.py` | The 6 tools the agent can call, including a "buy" button it must never press. |
| `prompt.py` | The agent's instructions (policies + habit rules). `v1` = baseline, `v2` = final version (same rules, better answer instructions). |
| `agent.py` | The agent loop. |
| `tests/test_cases.json` | The 43 test cases (1-21 base, 22-28 harder, 29-37 more complex, 38-43 in French, Spanish and Arabic) and what each must get right. |
| `grader.py` | Grades each answer with plain rules (no AI grader). |
| `oracle.py` | A scripted perfect answer per test, to prove the grader gives 100% to a perfect agent. |
| `run_tests.py` | Runs the tests and writes CSVs to `results/`. Can also re-score saved answers for free (`--regrade`). |
| `results/` | Every test run, numbered by step, with a guide (`results/README.md`). |
| `app.py` | Web page to try the agent (final version: Haiku 5.5 + prompt v2), with a password. |
| `requirements.txt` | Python libraries to install. |

## Run
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or AI71_API_KEY
python run_tests.py --model claude-haiku-5-5 --label final --repeat 3 --prompt v2   # final version
python run_tests.py --model claude-haiku-5-5 --label baseline --repeat 3            # baseline (prompt v1)
python run_tests.py --model claude-sonnet-5-5 --label sonnet --repeat 3             # variation 2
python run_tests.py --oracle                                                        # grader self-check, free
python run_tests.py --regrade results/7-variation1-haiku-prompt-v2                 # re-score saved answers, free
python agent.py nadia "Rome from 27 to 29 November, 1000 euros"   # one request (Sonnet, prompt v1)
```

## Web page
Try it locally: `streamlit run app.py` (needs the API key in the environment).

Host it on Streamlit Community Cloud (free):
1. Sign in at share.streamlit.io with GitHub.
2. Create app: this repo, branch `main`, file `app.py`.
3. In the app's Settings > Secrets, add:
   ```
   AI71_API_KEY = "..."
   APP_PASSWORD = "..."
   ```
4. Put a monthly spending cap on the API key in the Anthropic console.

The page runs Haiku 5.5 with prompt v2. The visitor picks one of the 8 test customers, or "Me" to set their own home city and travel habits (favourite airline and hotel brand, how often). It shows the answer, the trip rebuilt from the data, and every step the agent took. Max 30 requests per browser session.
