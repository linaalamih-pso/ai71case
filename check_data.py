"""Checks that the fake data supports every test case as intended.

For each test it lists what a perfect agent could propose, and checks the
traps (e.g. "the habit hotel is over budget") are really there.
Run: python check_data.py
"""

import json
from itertools import product
from pathlib import Path

import world

TESTS = json.loads((Path(__file__).parent / "tests" / "test_cases.json").read_text())


def all_trips(t, depart=None, ret=None):
    """Every valid (flight out, flight back, hotel, room) for a test, with its total."""
    n = t["travellers"]
    outs = [f for f in world.flights_on(t["origin"], t["destination"], depart or t["depart"]) if f["seats_left"] >= n]
    rets = [f for f in world.flights_on(t["destination"], t["origin"], ret or t["return"]) if f["seats_left"] >= n]
    trips = []
    for o, r in product(outs, rets):
        for h in world.HOTELS:
            if h["city"] != t["destination"]:
                continue
            for rm in h["rooms"]:
                rooms = -(-n // rm["max_guests"])  # rooms needed (rounded up)
                if rooms > rm["rooms_left"]:
                    continue
                total, _ = world.price_trip(o["id"], r["id"], h["id"], rm["type"], rooms, n)
                trips.append({"out": o, "ret": r, "hotel": h, "room": rm["type"], "rooms": rooms, "total": total})
    return trips


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  OK   " if cond else "  FAIL ") + msg)
        ok &= bool(cond)

    for t in TESTS:
        print(f"Test {t['id']}: {t['request']}")
        if t["expected_action"] == "ask":
            continue
        trips = all_trips(t)
        fits = [x for x in trips if x["total"] <= t["budget"]]
        cheapest = min((x["total"] for x in trips), default=None)
        print(f"  {len(trips)} possible trips, {len(fits)} within budget, cheapest = {cheapest}")
        if t["expected_action"] == "propose":
            check(fits, "at least one trip fits the budget")
        if t["id"] == 1 or t["id"] == 6:
            check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == "Air France"],
                  "an all-Air France trip fits the budget")
        if t["id"] in (2, 3):
            nicest = [x for x in trips if x["hotel"]["stars"] == 5 and x["out"]["stops"] == 0]
            check(nicest and all(x["total"] > t["budget"] for x in nicest),
                  "trap: every direct-flight + 5-star trip is over budget")
        if t["id"] == 4:
            forgot = [x for x in trips if x["total"] > t["budget"] and
                      x["total"] - (x["out"]["price_per_person_eur"] + x["ret"]["price_per_person_eur"]) <= t["budget"]]
            check(forgot, f"trap: {len(forgot)} trips look within budget if flights are counted once")
        if t["id"] in (7, 10):
            check([x for x in fits if x["hotel"]["brand"] == "Marriott"], "a Marriott trip fits the budget")
        if t["id"] == 8:
            check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == "easyJet"],
                  "an all-easyJet trip fits the budget")
        if t["id"] == 9:
            check([x for x in fits if x["hotel"]["brand"] == "Hilton"], "a Hilton trip fits the budget")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
        if t["id"] == 11:
            check([x for x in fits if not x["hotel"]["is_chain"]], "a non-chain hotel trip fits the budget")
        if t["id"] == 13:
            check(not [x for x in fits if x["hotel"]["brand"] == "Marriott"], "trap: no Marriott trip fits the budget")
        if t["id"] == 15:
            check(not fits, "trap: nothing fits €150")
        if t["id"] == 16:
            check(not trips, "trap: no data for Reykjavik")
        if t["id"] == 17:
            check(not world.flights_on("Rome", "Paris", "2026-12-25"), "trap: no Rome -> Paris flight on 25 Dec")
            for d in ("2026-12-24", "2026-12-26"):
                alt = [x for x in all_trips(t, depart=d) if x["total"] <= t["budget"]]
                check(alt, f"leaving {d} instead: {len(alt)} trips fit")
        if t["id"] == 21:
            check(all(x["room"] == "family" or x["rooms"] > 1 for x in trips), "every valid trip uses a family room or 2 rooms")
            tight = [f for f in world.flights_on("Porto", "Madrid", "2026-12-18") if f["seats_left"] < 3]
            check(tight, "trap: a Porto -> Madrid flight has fewer than 3 seats")
            family = [x for x in fits if x["rooms"] == 1]
            doubles = [x for x in fits if x["rooms"] == 2 and x["hotel"]["stars"] == 4]
            check(family and doubles and min(x["total"] for x in family if x["hotel"]["stars"] == 4)
                  < min(x["total"] for x in doubles), "at 4 stars, one family room is cheaper than 2 doubles")
        if t["id"] == 23:
            check(all(x["rooms"] >= 2 for x in trips), "trap: Rome has no room for 3, so every trip needs 2 rooms")
            check([x for x in fits if x["hotel"]["brand"] == "Hilton"], "a Hilton trip fits the budget")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
        if t["id"] == 24:
            check(len(fits) == 1, f"trap: exactly one trip fits ({len(fits)})")
        if t["id"] == 25:
            check([x for x in fits if x["hotel"]["area"] == "Barceloneta"], "a beach (Barceloneta) hotel fits")
            check([x for x in fits if x["hotel"]["brand"] == "Marriott"], "trap: the Marriott fits too, but isn't by the beach")
        if t["id"] == 26:
            solo = all_trips({**t, "travellers": 1})
            check([x for x in solo if x["hotel"]["brand"] == "Marriott" and x["total"] <= t["budget"]],
                  "trap: the Marriott fits the budget for 1 person")
            check(not [x for x in fits if x["hotel"]["brand"] == "Marriott"], "...but not for 2")
        if t["id"] == 28:
            for al in ("Air France", "easyJet"):
                check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == al
                       and x["out"]["stops"] == x["ret"]["stops"] == 0], f"a direct {al} trip fits the budget")
            stay = {x["hotel"]["brand"]: x["total"] - x["out"]["price_per_person_eur"] - x["ret"]["price_per_person_eur"]
                    for x in fits if x["room"] == "double" and x["hotel"]["stars"] == 4}
            check(stay.get("Marriott", 9e9) < stay.get("Hilton", 0), "Marriott is cheaper than Hilton (both 4 stars)")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


if __name__ == "__main__":
    main()
