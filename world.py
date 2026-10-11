"""The fake travel world: loads the JSON data and answers questions about it.

Used by both the agent's tools and the test script, so they always agree on
what exists and what it costs.
"""

import json
from datetime import date
from pathlib import Path

DATA = Path(__file__).parent / "data"
TODAY = "2026-10-11"  # "today" in the fake world

FLIGHTS = json.loads((DATA / "flights.json").read_text())
HOTELS = json.loads((DATA / "hotels.json").read_text())
USERS = json.loads((DATA / "users.json").read_text())

FLIGHTS_BY_ID = {f["id"]: f for f in FLIGHTS}
HOTELS_BY_ID = {h["id"]: h for h in HOTELS}
FLIGHT_CITIES = sorted({f["origin"] for f in FLIGHTS})
HOTEL_CITIES = sorted({h["city"] for h in HOTELS})


def nights(check_in, check_out):
    return (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days


def flights_on(origin, destination, day):
    return [f for f in FLIGHTS
            if f["origin"] == origin and f["destination"] == destination and f["date"] == day]


def find_room(hotel, room_type):
    return next((r for r in hotel["rooms"] if r["type"] == room_type), None)


def price_trip(outbound_id, return_id, hotel_id, room_type, rooms, travellers):
    """Recomputes a trip's real total from the data.

    Returns (total, problems). `problems` lists anything that doesn't exist
    in the data; total is None when the trip can't be priced.
    """
    problems = []
    out = FLIGHTS_BY_ID.get(outbound_id)
    ret = FLIGHTS_BY_ID.get(return_id)
    hotel = HOTELS_BY_ID.get(hotel_id)
    if not out:
        problems.append(f"outbound flight {outbound_id!r} does not exist")
    if not ret:
        problems.append(f"return flight {return_id!r} does not exist")
    if not hotel:
        problems.append(f"hotel {hotel_id!r} does not exist")
    rm = find_room(hotel, room_type) if hotel else None
    if hotel and not rm:
        problems.append(f"room type {room_type!r} does not exist at {hotel_id}")
    if problems:
        return None, problems
    n = nights(out["date"], ret["date"])
    total = ((out["price_per_person_eur"] + ret["price_per_person_eur"]) * travellers
             + rm["price_per_night_eur"] * n * rooms)
    return total, problems
