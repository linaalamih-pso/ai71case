# AI71 case: travel agent

A travel assistant for a digital bank. It reads a trip request, looks at the
customer's card payments for travel habits, searches fake flights and hotels,
and proposes one trip within budget. It never books.

Spec, decisions and test cases: `A71 case.md` (project files).

## Files
| File | What it is |
|---|---|
| `data/build_data.py` | Builds the fake world (flights, hotels, 7 test users). Fixed seed: same world every time. |
| `data/*.json` | The fake world itself. |
| `check_data.py` | Checks that every test's trap is really in the data. |
| `world.py` | Loads the data, recomputes trip prices. Shared by the agent and the grader. |
| `tools.py` | The 6 tools the agent can call, including a "buy" button it must never press. |
| `prompt.py` | The agent's instructions (policies + habit rules). |
| `agent.py` | The agent loop. |
| `tests/test_cases.json` | The 43 test cases (1-21 base, 22-28 harder, 29-37 more complex, 38-43 in French, Spanish and Arabic) and what each must get right. |
| `grader.py` | Grades each answer with plain rules (no AI grader). |
| `oracle.py` | A scripted perfect answer per test, to prove the grader gives 100% to a perfect agent. |
| `run_tests.py` | Runs the tests and writes CSVs to `results/`. |

## Run
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # or AI71_API_KEY
python run_tests.py                                   # 43 tests on Sonnet 5.5
python run_tests.py --model claude-haiku-5-5 --label haiku --repeat 3   # Haiku, every test 3 times
python run_tests.py --oracle                          # grader self-check, free
python agent.py nadia "Rome from 27 to 29 November, 1000 euros"   # one request
```
