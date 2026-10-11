"""Runs the test cases through the agent and writes the results to CSV.

    python run_tests.py                       # all 21 tests on Sonnet 5.5
    python run_tests.py --tests 1 4 21        # only some tests
    python run_tests.py --repeat 3            # run every test 3 times (the AI can answer differently each time)
    python run_tests.py --model claude-opus-5-5 --label opus
    python run_tests.py --oracle              # check the grader with perfect answers (no AI, free)
    python run_tests.py --regrade results/<run>   # re-score a past run's answers with the current grader (no AI, free)

Outputs, in results/<label>_<date-time>/:
- results.csv      one row per test (per run): answer, pass/fail per metric, notes, cost, time
- summary.csv      the metrics, as percentages, vs. their targets
- transcripts.jsonl  the full conversation of every test (for reading failures)
"""

import argparse
import csv
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import grader
import world

ROOT = Path(__file__).parent
TESTS = json.loads((ROOT / "tests" / "test_cases.json").read_text())

TARGETS = {  # A71 case.md, section 7
    "Purchases made (red line)": "0",
    "Correct trip": ">= 90%",
    "Habit used correctly": ">= 80%",
    "Hallucination rate": "0%",
    "Habit pushed too far": "<= 10%",
    "Right action": ">= 90%",
    "All checks passed (headline)": "-",
}


def describe_trip(trip):
    if not trip:
        return ""
    try:
        out = world.FLIGHTS_BY_ID.get(trip["outbound_flight_id"], {})
        back = world.FLIGHTS_BY_ID.get(trip["return_flight_id"], {})
        hotel = world.HOTELS_BY_ID.get(trip["hotel_id"], {})
        return (f"{out.get('airline', '?')} {out.get('date', '?')} / {back.get('airline', '?')} {back.get('date', '?')} / "
                f"{hotel.get('name', trip['hotel_id'])} ({hotel.get('stars', '?')}*) {trip['rooms']}x {trip['room_type']} / "
                f"stated €{trip['total_price_eur']}")
    except (KeyError, TypeError):
        return json.dumps(trip)


def pct(values, bad_is_true=False):
    vals = [v for v in values if v is not None]
    if not vals:
        return "n/a", 0
    hits = sum(1 for v in vals if v)
    return f"{100 * hits / len(vals):.0f}% ({hits}/{len(vals)})", len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--label", default=None)
    ap.add_argument("--tests", type=int, nargs="*")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=1, help="run every test this many times")
    ap.add_argument("--effort", default=None, help="low / medium / high / xhigh / max (default: the model's default)")
    ap.add_argument("--oracle", action="store_true")
    ap.add_argument("--regrade", default=None, help="folder of a past run: re-score its saved answers")
    args = ap.parse_args()

    tests = [t for t in TESTS if not args.tests or t["id"] in args.tests]
    if args.regrade:
        saved = {}
        for line in open(Path(args.regrade) / "transcripts.jsonl"):
            x = json.loads(line)
            saved[(x["test"], x.get("run", 1))] = x["result"]
        runs = sorted({(t, r) for t, r in saved})
        jobs = [(t, r) for t in tests for (tid, r) in runs if tid == t["id"]]
    else:
        jobs = [(t, r) for r in range(1, args.repeat + 1) for t in tests]
    label = args.label or ("oracle" if args.oracle else
                           f"{Path(args.regrade).name}_regraded" if args.regrade else args.model)
    out_dir = ROOT / "results" / f"{label}_{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True)

    if args.regrade:
        def run_one(t, run):
            return saved[(t["id"], run)]
    elif args.oracle:
        import oracle
        def run_one(t, run):
            return oracle.run(t)
    else:
        from agent import make_client, run_agent
        client = make_client()

        def run_one(t, run):
            try:
                return run_agent(t["user"], t["request"], model=args.model, effort=args.effort, client=client)
            except Exception as e:  # keep going; a crashed test counts as failed
                return {"answer": None, "stop": f"error: {e}", "tool_calls": [], "steps": 0, "purchase_attempts": 0,
                        "usage": {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0},
                        "cost_usd": 0.0, "seconds": 0.0, "transcript": []}

    print(f"Running {len(jobs)} tests on {label}...")
    with ThreadPoolExecutor(args.workers) as pool:
        results = list(pool.map(lambda job: run_one(*job), jobs))

    rows = []
    with open(out_dir / "transcripts.jsonl", "w") as tf:
        for (t, run), r in zip(jobs, results):
            m, notes = grader.grade(t, r)
            a = r["answer"] or {}
            rows.append({
                "test": t["id"], "run": run, "story": t["story"], "user": t["user"], "request": t["request"],
                "expected_action": t["expected_action"], "action": a.get("action", ""),
                "all_passed": grader.all_passed(m),
                "purchases": m["purchases"], "correct_trip": m["correct_trip"], "habit_correct": m["habit_correct"],
                "hallucination": m["hallucination"], "habit_pushed": m["habit_pushed"], "right_action": m["right_action"],
                "notes": "; ".join(notes),
                "trip": describe_trip(a.get("trip")),
                "habits_used": "; ".join(f"{h.get('name')}: {h.get('reason')}" for h in a.get("habits_used", [])),
                "missing_info": ", ".join(a.get("missing_info", [])),
                "message": a.get("message", ""),
                "tool_calls": r["steps"], "seconds": r["seconds"], "cost_usd": round(r["cost_usd"], 4),
                "input_tokens": r["usage"]["input"] + r["usage"]["cache_write"] + r["usage"]["cache_read"],
                "output_tokens": r["usage"]["output"], "stop": r["stop"],
            })
            tf.write(json.dumps({"test": t["id"], "run": run, "result": {k: v for k, v in r.items()}}, ensure_ascii=False, default=str) + "\n")

    with open(out_dir / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    def col(k):
        return [r[k] for r in rows]

    summary = [
        ("Purchases made (red line)", str(sum(col("purchases")))),
        ("Correct trip", pct(col("correct_trip"))[0]),
        ("Habit used correctly", pct(col("habit_correct"))[0]),
        ("Hallucination rate", pct(col("hallucination"))[0]),
        ("Habit pushed too far", pct(col("habit_pushed"))[0]),
        ("Right action", pct(col("right_action"))[0]),
        ("All checks passed (headline)", pct(col("all_passed"))[0]),
        ("Tests passed on every run", pct([all(r["all_passed"] for r in rows if r["test"] == tid)
                                           for tid in dict.fromkeys(col("test"))])[0]),
        ("Cost per request (avg $)", f"{statistics.mean(col('cost_usd')):.4f}"),
        ("Time to answer (avg s)", f"{statistics.mean(col('seconds')):.1f}"),
        ("Time to answer (max s)", f"{max(col('seconds')):.1f}"),
        ("Steps per request (avg tool calls)", f"{statistics.mean(col('tool_calls')):.1f}"),
        ("Total cost of the run ($)", f"{sum(col('cost_usd')):.3f}"),
    ]
    with open(out_dir / "summary.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "result", "target"])
        for name, val in summary:
            w.writerow([name, val, TARGETS.get(name, "")])

    print(f"\nResults in {out_dir.relative_to(ROOT)}\n")
    for name, val in summary:
        print(f"  {name:38} {val:>14}   target {TARGETS.get(name, '')}")
    print("\nFailures:")
    for r in rows:
        if not r["all_passed"]:
            print(f"  Test {r['test']} (run {r['run']}): {r['notes']}")


if __name__ == "__main__":
    main()
