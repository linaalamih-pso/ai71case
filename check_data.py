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
                rooms = -(-t.get("staying", n) // rm["max_guests"])  # rooms needed (rounded up)
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
        tid = t.get("translation_of", t["id"])  # a translated test has the same traps as its original
        if t["expected_action"] == "ask":
            continue
        trips = all_trips(t)
        fits = [x for x in trips if x["total"] <= t["budget"]]
        cheapest = min((x["total"] for x in trips), default=None)
        print(f"  {len(trips)} possible trips, {len(fits)} within budget, cheapest = {cheapest}")
        if t["expected_action"] == "propose":
            check(fits, "at least one trip fits the budget")
        if tid == 1 or tid == 6:
            check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == "Air France"],
                  "an all-Air France trip fits the budget")
        if tid in (2, 3):
            nicest = [x for x in trips if x["hotel"]["stars"] == 5 and x["out"]["stops"] == 0]
            check(nicest and all(x["total"] > t["budget"] for x in nicest),
                  "trap: every direct-flight + 5-star trip is over budget")
        if tid == 4:
            forgot = [x for x in trips if x["total"] > t["budget"] and
                      x["total"] - (x["out"]["price_per_person_eur"] + x["ret"]["price_per_person_eur"]) <= t["budget"]]
            check(forgot, f"trap: {len(forgot)} trips look within budget if flights are counted once")
        if tid in (7, 10):
            check([x for x in fits if x["hotel"]["brand"] == "Marriott"], "a Marriott trip fits the budget")
        if tid == 8:
            check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == "easyJet"],
                  "an all-easyJet trip fits the budget")
        if tid == 9:
            check([x for x in fits if x["hotel"]["brand"] == "Hilton"], "a Hilton trip fits the budget")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
        if tid == 11:
            check([x for x in fits if not x["hotel"]["is_chain"]], "a non-chain hotel trip fits the budget")
        if tid == 13:
            check(not [x for x in fits if x["hotel"]["brand"] == "Marriott"], "trap: no Marriott trip fits the budget")
        if tid == 15:
            check(not fits, "trap: nothing fits €150")
        if tid == 16:
            check(not trips, "trap: no data for Reykjavik")
        if tid == 17:
            check(not world.flights_on("Rome", "Paris", "2026-12-25"), "trap: no Rome -> Paris flight on 25 Dec")
            for d in ("2026-12-24", "2026-12-26"):
                alt = [x for x in all_trips(t, depart=d) if x["total"] <= t["budget"]]
                check(alt, f"leaving {d} instead: {len(alt)} trips fit")
        if tid == 21:
            check(all(x["room"] == "family" or x["rooms"] > 1 for x in trips), "every valid trip uses a family room or 2 rooms")
            tight = [f for f in world.flights_on("Porto", "Madrid", "2026-12-18") if f["seats_left"] < 3]
            check(tight, "trap: a Porto -> Madrid flight has fewer than 3 seats")
            family = [x for x in fits if x["rooms"] == 1]
            doubles = [x for x in fits if x["rooms"] == 2 and x["hotel"]["stars"] == 4]
            check(family and doubles and min(x["total"] for x in family if x["hotel"]["stars"] == 4)
                  < min(x["total"] for x in doubles), "at 4 stars, one family room is cheaper than 2 doubles")
        if tid == 23:
            check(all(x["rooms"] >= 2 for x in trips), "trap: Rome has no room for 3, so every trip needs 2 rooms")
            direct = [x for x in fits if x["out"]["stops"] == x["ret"]["stops"] == 0]
            check([x for x in direct if x["hotel"]["brand"] == "Hilton"], "a Hilton trip with direct flights fits the budget")
            check([x for x in direct if x["hotel"]["brand"] == "NH"], "the NH (same stars, a bit cheaper) fits too: Hilton breaks the tie")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
            check(not [x for x in direct if x["hotel"]["brand"] == "Marriott"], "the Marriott (4 stars) is over budget")
        if tid == 24:
            check(len(fits) == 1, f"trap: exactly one trip fits ({len(fits)})")
        if tid == 25:
            check([x for x in fits if x["hotel"]["area"] == "Barceloneta"], "a beach (Barceloneta) hotel fits")
            check([x for x in fits if x["hotel"]["brand"] == "Marriott"], "trap: the Marriott fits too, but isn't by the beach")
        if tid == 26:
            solo = all_trips({**t, "travellers": 1})
            check([x for x in solo if x["hotel"]["brand"] == "Marriott" and x["total"] <= t["budget"]],
                  "trap: the Marriott fits the budget for 1 person")
            check(not [x for x in fits if x["hotel"]["brand"] == "Marriott"], "...but not for 2")
        if tid == 28:
            for al in ("Air France", "easyJet"):
                check([x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == al
                       and x["out"]["stops"] == x["ret"]["stops"] == 0], f"a direct {al} trip fits the budget")
            stay = {x["hotel"]["brand"]: x["total"] - x["out"]["price_per_person_eur"] - x["ret"]["price_per_person_eur"]
                    for x in fits if x["room"] == "double" and x["hotel"]["stars"] == 4}
            check(stay.get("Marriott", 9e9) < stay.get("Hilton", 0), "Marriott is cheaper than Hilton (both 4 stars)")
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "no 5-star trip fits, so 4-star hotels compete")
        if tid == 29:
            check(not [x for x in trips if x["total"] <= t["budget"] / t["travellers"]],
                  "trap: read as a total for both (400), nothing fits")
        if tid == 30:
            ez = [x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == "easyJet"]
            check(ez and all(x["out"]["stops"] for x in ez), "trap: easyJet both ways fits, but the flight out stops")
            check([x for x in fits if x["out"]["stops"] == x["ret"]["stops"] == 0 and x["ret"]["airline"] == "easyJet"],
                  "a direct trip with easyJet back fits")
        if tid == 31:
            big = [h for h in world.HOTELS if h["city"] == "Rome" and h["stars"] == 5]
            check(all(r["rooms_left"] < 3 for h in big for r in h["rooms"]), "trap: the 5-star has fewer than 3 rooms left")
            af = [f for f in world.flights_on("Paris", "Rome", t["depart"]) if f["airline"] == "Air France"]
            af += [f for f in world.flights_on("Rome", "Paris", t["return"]) if f["airline"] == "Air France"]
            five = sum(f["price_per_person_eur"] for f in af) * 6 + big[0]["rooms"][0]["price_per_night_eur"] * 2 * 3
            check(five <= t["budget"], f"trap: Air France + 5-star would fit the budget (€{five}) if rooms were left")
            check([x for x in fits if x["hotel"]["brand"] == "Hilton" and x["out"]["airline"] == "Air France"],
                  "Air France + Hilton fits")
        if tid == 32:
            check(not [x for x in fits if x["hotel"]["stars"] == 5], "the 5-star is over budget")
            check(not [x for x in fits if x["hotel"]["brand"] == "Marriott"], "trap: the Marriott habit is over budget")
        if tid == 33:
            check([x for x in fits if x["hotel"]["brand"] == "Marriott"], "a Marriott trip fits 1.2k")
        if tid == 34:
            five = [x for x in trips if x["hotel"]["stars"] == 5]
            check(five and not [x for x in five if x["total"] <= t["budget"]], "trap: no 5-star trip fits")
            check(min(x["total"] for x in five) - t["budget"] < 50, "...but the cheapest 5-star is just over")
            check([x for x in fits if x["hotel"]["stars"] == 4], "a 4-star trip fits (the tempting wrong answer)")
        if tid == 36:
            check(all(x["rooms"] == 2 for x in trips), "rooms for 4 in Lisbon = 2 doubles")
            four = all_trips({**t, "travellers": 4})
            check(not [x for x in four if x["total"] <= t["budget"] and x["hotel"]["brand"] == "Hilton"
                       and x["out"]["airline"] == "Air France"], "trap: with 4 seats, Air France + Hilton is over budget")
            check([x for x in fits if x["hotel"]["brand"] == "Hilton" and x["out"]["airline"] == x["ret"]["airline"] == "Air France"],
                  "Air France + Hilton fits with 2 seats and 2 rooms")
        if tid == 37:
            check(all(x["rooms"] >= 2 for x in trips), "trap: no room holds 5")
            check(not [x for x in trips if x["hotel"]["brand"] == "Marriott" and x["room"] == "family"],
                  "trap: the Marriott family room has only 1 left")
            check([x for x in fits if x["hotel"]["stars"] == 4], "a 4-star option fits (Hilton, 3 doubles)")
    print("\nALL CHECKS PASSED" if ok else "\nSOME CHECKS FAILED")


if __name__ == "__main__":
    main()
