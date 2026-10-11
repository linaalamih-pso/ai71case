"""Builds the fake travel world: flights, hotels and test users.

Run once with `python data/build_data.py`. The output is deterministic (fixed
random seed), so every test run sees exactly the same world.

A few values are set by hand on purpose: they are the "traps" the test cases
rely on (see the comments marked TRAP).
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).parent
random.seed(71)

CITIES = ["Paris", "Lyon", "Madrid", "Valencia", "Barcelona", "Lisbon", "Porto", "Rome"]
CODES = {"Paris": "PAR", "Lyon": "LYS", "Madrid": "MAD", "Valencia": "VLC",
         "Barcelona": "BCN", "Lisbon": "LIS", "Porto": "OPO", "Rome": "ROM"}

# Rough one-way "base fare" per city pair, in euros (symmetric).
BASE = {
    ("Paris", "Lyon"): 70, ("Paris", "Madrid"): 95, ("Paris", "Valencia"): 95,
    ("Paris", "Barcelona"): 90, ("Paris", "Lisbon"): 115, ("Paris", "Porto"): 105,
    ("Paris", "Rome"): 105, ("Lyon", "Madrid"): 95, ("Lyon", "Valencia"): 90,
    ("Lyon", "Barcelona"): 80, ("Lyon", "Lisbon"): 115, ("Lyon", "Porto"): 110,
    ("Lyon", "Rome"): 90, ("Madrid", "Valencia"): 60, ("Madrid", "Barcelona"): 70,
    ("Madrid", "Lisbon"): 75, ("Madrid", "Porto"): 70, ("Madrid", "Rome"): 105,
    ("Valencia", "Barcelona"): 60, ("Valencia", "Lisbon"): 85, ("Valencia", "Porto"): 85,
    ("Valencia", "Rome"): 90, ("Barcelona", "Lisbon"): 90, ("Barcelona", "Porto"): 85,
    ("Barcelona", "Rome"): 85, ("Lisbon", "Porto"): 55, ("Lisbon", "Rome"): 115,
    ("Porto", "Rome"): 115,
}

# Airline -> (home cities where it is based, price factor vs base fare)
AIRLINES = {
    "Air France": (["Paris", "Lyon"], 1.45),  # (hubs, price factor)
    "Iberia": (["Madrid", "Valencia"], 1.35),
    "TAP Air Portugal": (["Lisbon", "Porto"], 1.30),
    "ITA Airways": (["Rome"], 1.35),
    "Vueling": (["Barcelona"], 0.95),
    "easyJet": (CITIES, 0.85),        # flies everywhere
    "Ryanair": (CITIES, 0.70),        # flies everywhere, but not every day
}
FLIGHT_CODES = {"Air France": "AF", "Iberia": "IB", "TAP Air Portugal": "TP", "ITA Airways": "AZ",
                "Vueling": "VY", "easyJet": "U2", "Ryanair": "FR"}
RYANAIR_DAYS = {1, 3, 5}  # Tue, Thu, Sat

START, END = date(2026, 10, 20), date(2027, 1, 10)


def base_fare(a, b):
    return BASE.get((a, b)) or BASE[(b, a)]


def build_flights():
    flights = []
    d = START
    while d <= END:
        for origin in CITIES:
            for dest in CITIES:
                if origin == dest:
                    continue
                for airline, (hubs, factor) in AIRLINES.items():
                    if origin not in hubs and dest not in hubs:
                        continue
                    if airline == "Ryanair" and d.weekday() not in RYANAIR_DAYS:
                        continue
                    # Prices go up a bit near Christmas and on Fridays/Sundays.
                    season = 1.25 if date(2026, 12, 18) <= d <= date(2027, 1, 3) else 1.0
                    weekday = 1.10 if d.weekday() in (4, 6) else 1.0
                    noise = random.uniform(0.9, 1.15)
                    price = round(base_fare(origin, dest) * factor * season * weekday * noise)
                    stops = 0
                    if airline in ("easyJet", "Ryanair") and random.random() < 0.15:
                        stops = 1
                    hour = random.choice([6, 7, 8, 9, 11, 13, 15, 17, 19, 21])
                    minute = random.choice([0, 15, 30, 45])
                    flights.append({
                        "id": f"{FLIGHT_CODES[airline]}-{CODES[origin]}{CODES[dest]}-{d:%m%d}",
                        "airline": airline,
                        "origin": origin,
                        "destination": dest,
                        "date": d.isoformat(),
                        "departure_time": f"{hour:02d}:{minute:02d}",
                        "stops": stops,
                        "price_per_person_eur": price,
                        "seats_left": random.randint(3, 9),
                    })
        d += timedelta(days=1)

    # TRAP test 17: no flight at all from Rome to Paris on Christmas Day.
    flights = [f for f in flights
               if not (f["origin"] == "Rome" and f["destination"] == "Paris" and f["date"] == "2026-12-25")]

    # TRAP test 21: the cheapest Porto -> Madrid flight on 18 Dec has only
    # 2 seats left, so it can't carry a family of 3.
    porto_mad = [f for f in flights if f["origin"] == "Porto" and f["destination"] == "Madrid"
                 and f["date"] == "2026-12-18"]
    cheapest = min(porto_mad, key=lambda f: f["price_per_person_eur"])
    cheapest["seats_left"] = 2

    return flights


def room(kind, guests, price, left):
    return {"type": kind, "max_guests": guests, "price_per_night_eur": price, "rooms_left": left}


def hotel(hid, name, city, brand, stars, area, rooms, style=None):
    return {"id": hid, "name": name, "city": city, "brand": brand,
            "is_chain": brand != "Independent", "style": style or ("chain" if brand != "Independent" else "independent"),
            "stars": stars, "area": area, "rooms": rooms}


def build_hotels():
    return [
        # Paris
        hotel("PAR-H1", "Le Grand Palais Royal", "Paris", "Independent", 5, "Louvre",
              [room("double", 2, 520, 3)], "grand hotel"),  # TRAP test 2: nicest hotel over budget
        hotel("PAR-H2", "Paris Marriott Opera", "Paris", "Marriott", 4, "Opera",
              [room("double", 2, 300, 4), room("family", 4, 470, 1)]),
        hotel("PAR-H3", "Hilton Paris Bastille", "Paris", "Hilton", 4, "Bastille",
              [room("double", 2, 245, 5)]),
        hotel("PAR-H4", "Hotel des Petits Boulevards", "Paris", "Independent", 4, "Le Marais",
              [room("double", 2, 230, 2)], "boutique"),
        hotel("PAR-H5", "Novotel Paris Gare de Lyon", "Paris", "Accor", 3, "Gare de Lyon",
              [room("double", 2, 165, 8), room("family", 4, 230, 3)]),
        hotel("PAR-H6", "ibis Paris Montmartre", "Paris", "Accor", 2, "Montmartre",
              [room("double", 2, 105, 10)]),

        # Rome
        hotel("ROM-H1", "Hotel Palazzo Aurelia", "Rome", "Independent", 5, "Via Veneto",
              [room("double", 2, 560, 2)], "grand hotel"),  # TRAP test 3
        hotel("ROM-H2", "Rome Marriott Flora", "Rome", "Marriott", 4, "Villa Borghese",
              [room("double", 2, 310, 4)]),  # TRAP test 13: habit hotel over budget
        hotel("ROM-H3", "Hilton Rome Spagna", "Rome", "Hilton", 4, "Spanish Steps",
              [room("double", 2, 235, 4)]),  # TRAP test 9: Hilton ...
        hotel("ROM-H4", "NH Collection Roma Centro", "Rome", "NH", 4, "Centro Storico",
              [room("double", 2, 225, 4)]),  # ... and a similar non-Hilton
        hotel("ROM-H5", "Casa Trastevere", "Rome", "Independent", 3, "Trastevere",
              [room("double", 2, 140, 2)], "boutique"),
        hotel("ROM-H6", "ibis Roma Termini", "Rome", "Accor", 2, "Termini",
              [room("double", 2, 95, 9)]),

        # Barcelona
        hotel("BCN-H1", "Hotel Mirador Barcelona", "Barcelona", "Independent", 5, "Passeig de Gracia",
              [room("double", 2, 430, 3)], "grand hotel"),
        hotel("BCN-H2", "Barcelona Marriott Diagonal", "Barcelona", "Marriott", 4, "Diagonal",
              [room("double", 2, 230, 5)]),
        hotel("BCN-H3", "Hilton Barcelona Mar", "Barcelona", "Hilton", 4, "Barceloneta",
              [room("double", 2, 220, 5)]),
        hotel("BCN-H4", "Casa Gracia Boutique", "Barcelona", "Independent", 4, "Gracia",
              [room("double", 2, 190, 2)], "boutique"),  # test 11: the non-chain option
        hotel("BCN-H5", "Novotel Barcelona City", "Barcelona", "Accor", 3, "Poblenou",
              [room("double", 2, 140, 6)]),
        hotel("BCN-H6", "ibis Barcelona Centro", "Barcelona", "Accor", 2, "Eixample",
              [room("double", 2, 95, 8)]),

        # Lisbon
        hotel("LIS-H1", "Palacio Tejo", "Lisbon", "Independent", 5, "Chiado",
              [room("double", 2, 480, 2)], "grand hotel"),
        hotel("LIS-H2", "Lisbon Marriott Parque", "Lisbon", "Marriott", 4, "Avenidas Novas",
              [room("double", 2, 210, 5)]),
        hotel("LIS-H3", "Hilton Lisbon Liberdade", "Lisbon", "Hilton", 4, "Avenida da Liberdade",
              [room("double", 2, 220, 4)]),
        hotel("LIS-H4", "Casa do Bairro", "Lisbon", "Independent", 3, "Alfama",
              [room("double", 2, 150, 2)], "boutique"),
        hotel("LIS-H5", "Novotel Lisboa", "Lisbon", "Accor", 3, "Sete Rios",
              [room("double", 2, 130, 6)]),
        hotel("LIS-H6", "ibis Lisboa Centro", "Lisbon", "Accor", 2, "Saldanha",
              [room("double", 2, 85, 9)]),

        # Madrid (family rooms matter for test 21)
        hotel("MAD-H1", "Gran Hotel Retiro", "Madrid", "Independent", 5, "Retiro",
              [room("double", 2, 400, 3), room("family", 4, 650, 1)], "grand hotel"),
        hotel("MAD-H2", "Madrid Marriott Castellana", "Madrid", "Marriott", 4, "Castellana",
              [room("double", 2, 200, 5), room("family", 4, 320, 2)]),
        hotel("MAD-H3", "Hilton Madrid Gran Via", "Madrid", "Hilton", 4, "Gran Via",
              [room("double", 2, 210, 4)]),
        hotel("MAD-H4", "NH Collection Madrid Sol", "Madrid", "NH", 4, "Sol",
              [room("double", 2, 190, 4), room("family", 4, 290, 2)]),
        hotel("MAD-H5", "Hostal Lavapies", "Madrid", "Independent", 3, "Lavapies",
              [room("double", 2, 120, 2)], "boutique"),
        hotel("MAD-H6", "ibis Madrid Centro", "Madrid", "Accor", 2, "Centro",
              [room("double", 2, 90, 9), room("family", 3, 140, 3)]),
    ]


def pay(d, merchant, category, amount):
    return {"date": d, "merchant": merchant, "category": category, "amount_eur": amount}


# Today in the fake world is 2026-10-11. "Last 12 months" = since 2025-10-11.
USERS = {
    "nadia": {
        "name": "Nadia", "home_city": "Paris",
        "card_payments": [
            pay("2025-11-14", "AIR FRANCE", "airline", 312.40),
            pay("2026-03-02", "AIR FRANCE", "airline", 268.10),
            pay("2026-07-19", "AIR FRANCE", "airline", 401.00),
            pay("2025-06-08", "HILTON LONDON TOWER BRIDGE", "hotel", 486.00),
            pay("2026-03-05", "HILTON BRUSSELS GRAND PLACE", "hotel", 352.50),
        ],
    },
    "maxim": {"name": "Maxim", "home_city": "Madrid", "card_payments": []},
    "karim": {
        "name": "Karim", "home_city": "Madrid",
        "card_payments": [
            pay("2025-02-21", "HILTON AMSTERDAM", "hotel", 410.00),
            pay("2026-05-09", "HILTON MILAN", "hotel", 295.80),
        ],
    },
    "sofia": {
        "name": "Sofia", "home_city": "Lyon",
        "card_payments": [
            pay("2024-12-03", "MARRIOTT VIENNA", "hotel", 380.00),
            pay("2025-04-18", "MARRIOTT BERLIN", "hotel", 455.20),
            pay("2025-09-27", "COURTYARD BY MARRIOTT GENEVA", "hotel", 298.00),
            pay("2026-06-12", "MARRIOTT AMSTERDAM", "hotel", 520.00),
            pay("2026-02-14", "IBERIA", "airline", 245.60),
        ],
    },
    "tom": {
        "name": "Tom", "home_city": "Rome",
        "card_payments": [
            pay("2025-12-20", "EASYJET", "airline", 142.00),
            pay("2026-04-03", "EASYJET", "airline", 118.50),
            pay("2026-08-28", "EASYJET", "airline", 176.30),
            pay("2025-09-15", "ACCOR - NOVOTEL MILANO", "hotel", 189.00),
        ],
    },
    "lea": {
        "name": "Léa", "home_city": "Valencia",
        "card_payments": [
            pay("2024-11-22", "MARRIOTT LONDON", "hotel", 610.00),
            pay("2025-03-08", "MARRIOTT PARIS", "hotel", 455.00),
            pay("2025-07-30", "MARRIOTT NICE", "hotel", 390.00),
            pay("2026-01-17", "MARRIOTT MUNICH", "hotel", 342.00),
            pay("2026-07-05", "MARRIOTT ATHENS", "hotel", 498.00),
        ],
    },
    "ines": {"name": "Inès", "home_city": "Porto", "card_payments": []},
    # Test 28: two strong airlines (Air France used most) and two medium hotel brands.
    "hugo": {
        "name": "Hugo", "home_city": "Paris",
        "card_payments": [
            pay("2025-11-28", "AIR FRANCE", "airline", 298.00),
            pay("2026-02-06", "AIR FRANCE", "airline", 334.50),
            pay("2026-05-15", "AIR FRANCE", "airline", 287.20),
            pay("2026-09-04", "AIR FRANCE", "airline", 352.00),
            pay("2026-01-23", "EASYJET", "airline", 131.40),
            pay("2026-06-26", "EASYJET", "airline", 158.90),
            pay("2025-03-14", "HILTON LISBON", "hotel", 344.00),
            pay("2026-04-10", "HILTON VIENNA", "hotel", 412.00),
            pay("2025-08-22", "MARRIOTT PRAGUE", "hotel", 376.00),
            pay("2026-07-31", "COURTYARD BY MARRIOTT ROME", "hotel", 301.50),
        ],
    },
}


def main():
    flights = build_flights()
    hotels = build_hotels()
    (OUT / "flights.json").write_text(json.dumps(flights, indent=1, ensure_ascii=False))
    (OUT / "hotels.json").write_text(json.dumps(hotels, indent=1, ensure_ascii=False))
    (OUT / "users.json").write_text(json.dumps(USERS, indent=1, ensure_ascii=False))
    print(f"{len(flights)} flights, {len(hotels)} hotels, {len(USERS)} users")


if __name__ == "__main__":
    main()
