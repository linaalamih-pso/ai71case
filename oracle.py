"""A scripted "perfect agent" that answers every test straight from the data.

It doesn't use AI. Its only job is to check the test script: a perfect
answer must score 100%. If it doesn't, the grader (not the agent) is wrong.
Run: python run_tests.py --oracle
"""

import world
from check_data import all_trips


# The same perfect answer, in the customer's language (tests 38-43).
LOCAL = {
    "fr": "Voici votre voyage pour {total} €, dans votre budget de {budget} €. Vous prenez souvent {names}, donc "
          "je l'ai choisi. Il vous reste {left} € : je peux proposer un meilleur hôtel. Vous pouvez le réserver "
          "vous-même quand vous voulez.",
    "es": "Aquí está su viaje por {total} €, dentro de su presupuesto de {budget} €. Le quedan {left} €: puedo "
          "proponer un hotel mejor. Puede reservarlo usted mismo cuando quiera.",
    "ar": "هذه رحلتك بسعر {total} يورو، ضمن ميزانيتك البالغة {budget} يورو. أنت تسافر كثيراً مع {names}، لذلك "
          "اخترتها. يتبقى لك {left} يورو، ويمكنني اقتراح فندق أفضل. يمكنك حجزها بنفسك متى شئت.",
}


def _pick(test, trips):
    fits = [x for x in trips if x["total"] <= test["budget"]]
    hf = test.get("habit_follow", {})
    if "airline" in hf:
        fits = [x for x in fits if x["out"]["airline"] == x["ret"]["airline"] == hf["airline"]] or fits
    if "hotel_brand" in hf:
        fits = [x for x in fits if x["hotel"]["brand"] == hf["hotel_brand"]] or fits
    if test.get("habit_not", {}).get("hotel_is_chain"):
        fits = [x for x in fits if not x["hotel"]["is_chain"]]
    if test.get("habit_not", {}).get("hotel_brand"):
        fits = [x for x in fits if x["hotel"]["brand"] != test["habit_not"]["hotel_brand"]]
    from grader import check_trip
    fits = [x for x in fits if not check_trip(test, _trip(test, x))[1]]  # meets every "must be true"
    return min(fits, key=lambda x: x["total"])


def _left(test, total):
    """The budget sentence the quality rules ask for (75% / 90% thresholds)."""
    left = test["budget"] - total
    if total < 0.75 * test["budget"]:
        return f"You still have €{left} left, so I can suggest a better hotel if you like. "
    if total < 0.9 * test["budget"]:
        return f"That leaves €{left} of your budget. "
    return ""


def _trip(test, x):
    return {"outbound_flight_id": x["out"]["id"], "return_flight_id": x["ret"]["id"], "hotel_id": x["hotel"]["id"],
            "room_type": x["room"], "rooms": x["rooms"], "travellers": test["travellers"], "staying": test.get("staying", test["travellers"]),
            "total_price_eur": x["total"]}


def answer(test):
    exp = test["expected_action"]
    if exp == "ask":
        words = {"dates": "your exact travel dates", "budget": "your budget", "child_age": "your child's age"}
        return {"action": "ask", "message": "To find your trip, I need " +
                " and ".join(words[m] for m in test["missing_must"]) + ".",
                "trip": None, "habits_used": [], "missing_info": test["missing_must"]}
    if exp == "nothing_fits":
        if test["closest"] == "none":
            return {"action": "nothing_fits", "trip": None, "habits_used": [], "missing_info": [],
                    "message": f"I have no data for {test['destination']}. I cover: {', '.join(world.HOTEL_CITIES)}."}
        if test["closest"] == "other_dates":
            from grader import _shift
            trips = all_trips(test, depart=_shift(test["depart"], 1), ret=_shift(test["return"], 1))
        else:
            trips = [x for x in all_trips(test)
                     if x["hotel"]["stars"] >= test.get("closest_must", {}).get("min_stars", 0)]
        x = min(trips, key=lambda x: x["total"])
        return {"action": "nothing_fits", "trip": _trip(test, x), "habits_used": [], "missing_info": [],
                "message": f"Nothing fits €{test['budget']}. The closest option costs €{x['total']}. "
                           "You could raise the budget or change dates."}
    x = _pick(test, all_trips(test))
    habits = [{"kind": "airline" if k == "airline" else "hotel", "name": v, "reason": "5 stays / trips"}
              for k, v in test.get("habit_follow", {}).items() if v in test.get("habit_cite", [])]
    names = " and ".join(h["name"] for h in habits)
    msg = (f"Here is your trip for €{x['total']}, within your €{test['budget']} budget. "
           + (f"You often use {names} (5 times), so I picked it. " if habits else "")
           + "".join(f"You also often use {w}. " for w in test.get("habit_message_all", []))
           + _left(test, x["total"])
           + ("" if test["origin"].lower() in test["request"].lower()
              else f"You leave from your home city, {test['origin']}. ")
           + "You can book it yourself whenever you're ready.")
    if test.get("language") in LOCAL:
        msg = LOCAL[test["language"]].format(total=x["total"], budget=test["budget"], names=names or "-",
                                             left=test["budget"] - x["total"])
    return {"action": "propose", "trip": _trip(test, x), "habits_used": habits, "missing_info": [], "message": msg}


def run(test):
    return {"answer": answer(test), "stop": "submitted", "tool_calls": [], "steps": 0, "purchase_attempts": 0,
            "usage": {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}, "cost_usd": 0.0,
            "seconds": 0.0, "transcript": []}
