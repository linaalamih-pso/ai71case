"""Web page to try the travel agent (Streamlit).

Run locally:   streamlit run app.py
Hosted on Streamlit Community Cloud. Two private settings ("secrets"):
    AI71_API_KEY = "..."     # the Anthropic API key (put a spending cap on it)
    APP_PASSWORD = "..."     # optional: asks for this password before showing the page

The page runs the frozen final version: Haiku 5.5 + prompt v2.
"""

import os
import re
import uuid
from collections import Counter
from datetime import date, timedelta

import streamlit as st

import world
from agent import run_agent, make_client
from grader import language
from prompt import PROMPTS

MODEL = "claude-haiku-5-5"
PROMPT = "v2"
MAX_REQUESTS = 30  # per browser session, to keep costs bounded

EXAMPLES = [
    ("nadia", "Lisbon from 20 to 22 November for me and my partner, 1200 euros"),
    ("hugo", "Rome from 4 to 6 December, 900 euros"),
    ("karim", "Barcelona with my wife and our 2 kids from 18 to 21 December, 2500 euros"),
    ("tom", "A long weekend in Lisbon mid-November, 700 euros"),
    ("sofia", "Barcelone du 20 au 22 novembre, budget 600 €"),
]

st.set_page_config(page_title="Travel agent", page_icon="✈️", layout="centered")


def secret(name):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:  # no secrets file when run locally
        return os.environ.get(name)


# --- Password gate -----------------------------------------------------------
password = secret("APP_PASSWORD")
if password and not st.session_state.get("unlocked"):
    st.title("✈️ Travel agent")
    typed = st.text_input("Password", type="password")
    if typed:
        if typed == password:
            st.session_state.unlocked = True
            st.rerun()
        st.error("Wrong password.")
    st.stop()

key = secret("AI71_API_KEY") or secret("ANTHROPIC_API_KEY")
if key:
    os.environ["AI71_API_KEY"] = key


# --- "Me": a profile the visitor builds, turned into fake card payments -------
AIRLINES = sorted({f["airline"] for f in world.FLIGHTS})
HOTEL_BRANDS = ["Hilton", "Marriott", "Novotel", "ibis", "NH"]
ELSEWHERE = ["VIENNA", "BERLIN", "PRAGUE", "LONDON", "AMSTERDAM", "BRUSSELS"]  # cities not in the data


def make_profile(name, city, airline, trips, brand, stays):
    """Fake card payments matching what the visitor chose: trips spread over the
    last 12 months, hotel stays over the last 24 months."""
    today = date.fromisoformat(world.TODAY)
    payments = []
    for i in range(trips if airline else 0):
        day = today - timedelta(days=30 + i * 330 // max(trips, 1))
        payments.append({"date": day.isoformat(), "merchant": airline.upper(), "category": "airline",
                         "amount_eur": 180.0 + 37 * i})
    for i in range(stays if brand else 0):
        day = today - timedelta(days=60 + i * 600 // max(stays, 1))
        payments.append({"date": day.isoformat(), "merchant": f"{brand.upper()} {ELSEWHERE[i % len(ELSEWHERE)]}",
                         "category": "hotel", "amount_eur": 260.0 + 45 * i})
    return {"name": name or "Guest", "home_city": city, "card_payments": sorted(payments, key=lambda p: p["date"])}


# --- Sidebar: who is asking, and what the fake world contains ----------------
def history(user):
    """'Air France x4, easyJet x2' from the card payments."""
    counts = Counter(p["merchant"].title() for p in user["card_payments"])
    return ", ".join(f"{m} x{n}" for m, n in counts.most_common()) or "no travel payments"


with st.sidebar:
    st.header("Customer")
    personas = [u for u in world.USERS if not u.startswith("me-")]
    st.session_state.setdefault("user_id", personas[0])
    user_id = st.selectbox("Who is asking?", ["me"] + personas, key="user_id",
                           format_func=lambda u: "Me: create my profile" if u == "me"
                           else f"{world.USERS[u]['name']} ({world.USERS[u]['home_city']})")
    if user_id == "me":
        name = st.text_input("Your first name", value="Alex")
        city = st.selectbox("You live in", world.FLIGHT_CITIES, index=world.FLIGHT_CITIES.index("Paris"))
        airline = st.selectbox("Airline you fly most", ["None"] + AIRLINES, index=1 + AIRLINES.index("Air France"))
        trips = st.slider("Round trips with it, last 12 months", 0, 6, 3, help="2 or more = strong habit")
        brand = st.selectbox("Hotel brand you stay with most", ["None"] + HOTEL_BRANDS, index=1)
        stays = st.slider("Stays with it, last 24 months", 0, 6, 2, help="3 or more = strong habit, 2 = tie-breaker")
        # One profile per browser session, so visitors don't overwrite each other
        st.session_state.setdefault("me_id", f"me-{uuid.uuid4().hex[:8]}")
        user_id = st.session_state.me_id
        world.USERS[user_id] = make_profile(name, city, None if airline == "None" else airline, trips,
                                            None if brand == "None" else brand, stays)
    user = world.USERS[user_id]
    st.caption(f"**Lives in:** {user['home_city']}")
    st.caption(f"**Travel card payments:** {history(user)}")

    st.header("What the agent can search")
    st.caption(f"Today is {world.TODAY} in this fake world.")
    st.caption("**Hotels in:** " + ", ".join(world.HOTEL_CITIES))
    st.caption("**Flights from:** " + ", ".join(world.FLIGHT_CITIES))
    st.caption("**Dates:** 20 October 2026 to 10 January 2027")
    st.caption("The data is made up. The agent proposes trips and never books.")


# --- Main page -----------------------------------------------------------------
st.title("✈️ Travel agent")
with st.expander("About this prototype", expanded=True):
    st.markdown(f"""
This is a prototype of a travel assistant for a digital bank. Ask for a trip as a customer would.
The agent searches flights and hotels, checks the budget, uses the customer's card history as a hint,
and proposes one trip. **It never books.** Any language works.

**It runs on a small, made-up data set.**
- **Hotels** in {len(world.HOTEL_CITIES)} cities: {", ".join(world.HOTEL_CITIES)}.
- **Flights** between these cities, plus {", ".join(c for c in world.FLIGHT_CITIES if c not in world.HOTEL_CITIES)}.
- **Dates:** trips from 20 October 2026 to 10 January 2027. "Today" is 11 October 2026.

A request outside this (another city, other dates) gets an answer saying it is not covered.

**Pick a customer** in the left panel (on a phone, tap the arrow at the top left).
Each one has past card payments that the agent uses as a soft preference. An explicit request always wins.

| Customer | Lives in | Card history | Good to test |
|---|---|---|---|
| Nadia | Paris | Air France often, 2 Hilton stays | Airline habit, hotel tie-break |
| Hugo | Paris | Air France and easyJet, Hilton and Marriott | Two habits competing |
| Tom | Rome | easyJet often | Airline habit |
| Sofia | Lyon | Marriott often | Hotel habit |
| Léa | Valencia | Marriott often | Hotel habit |
| Karim | Madrid | 2 Hilton stays | Hotel tie-break only |
| Maxim, Inès | Madrid, Porto | None | No habits |

**Or create your own customer.** Choose "Me: create my profile" at the top of the customer list,
then set your city, the airline you fly and the hotel brand you use. The page turns this into fake card payments.

Limits: {MAX_REQUESTS} requests per visit, about 10 seconds per answer.
""")

with st.expander("Example requests"):
    for uid, text in EXAMPLES:
        if st.button(f"{world.USERS[uid]['name']}: {text}", key=text):
            st.session_state.user_id = uid
            st.session_state.request = text
            st.rerun()

request = st.text_area("Your request", key="request", height=90,
                       placeholder="Rome from 27 to 29 November, 1000 euros")

used = st.session_state.get("used", 0)
go = st.button("Find a trip", type="primary", disabled=not request.strip() or used >= MAX_REQUESTS)
if used >= MAX_REQUESTS:
    st.info("Request limit reached for this session.")

if go:
    if not key:
        st.error("No API key configured.")
        st.stop()
    st.session_state.used = used + 1
    with st.spinner("The agent is searching... (about 10 seconds)"):
        try:
            st.session_state.result = run_agent(user_id, request, model=MODEL,
                                                system_prompt=PROMPTS[PROMPT], client=make_client())
        except Exception as e:
            st.session_state.result = None
            st.error(f"Something went wrong: {e}")


def trip_lines(trip):
    """The trip as plain lines, rebuilt from the data (not from the agent's text)."""
    out = world.FLIGHTS_BY_ID.get(trip.get("outbound_flight_id"))
    ret = world.FLIGHTS_BY_ID.get(trip.get("return_flight_id"))
    hotel = world.HOTELS_BY_ID.get(trip.get("hotel_id"))
    lines = []
    for label, f in (("Departure", out), ("Return", ret)):
        if f:
            stops = "direct" if f["stops"] == 0 else f"{f['stops']} stop(s)"
            lines.append(f"**{label}:** {f['airline']}, {f['origin']} → {f['destination']}, "
                         f"{f['date']} at {f['departure_time']}, {stops}, €{f['price_per_person_eur']} per person")
    if hotel:
        lines.append(f"**Hotel:** {hotel['name']}, {hotel['stars']}★, {hotel['area']}, {trip.get('rooms')} x {trip.get('room_type')}")
    total, problems = world.price_trip(trip.get("outbound_flight_id"), trip.get("return_flight_id"),
                                       trip.get("hotel_id"), trip.get("room_type"),
                                       trip.get("rooms", 1), trip.get("travellers", 1))
    if total is not None:
        lines.append(f"**Total (checked against the data):** €{total:,.0f} for {trip.get('travellers')} traveller(s)")
    lines += [f"⚠️ {p}" for p in problems]
    return lines


def step_label(call):
    a = call["input"]
    return {
        "get_user_profile": "Read the customer's profile (name, home city)",
        "get_card_payments": "Read the customer's travel card payments",
        "search_flights": f"Searched flights {a.get('origin')} → {a.get('destination')} on {a.get('date')}",
        "search_hotels": f"Searched hotels in {a.get('city')}, {a.get('check_in')} to {a.get('check_out')}",
        "book_trip": "Tried to book (blocked: booking is disabled)",
        "submit_answer": "Sent the answer",
    }.get(call["tool"], call["tool"])


def last_text(transcript):
    for m in reversed(transcript):
        if m["role"] == "assistant" and not isinstance(m["content"], str):
            text = " ".join(c.get("text", "") for c in m["content"] if c.get("type") == "text").strip()
            # Sometimes the "plain text" is a written-out call: submit_answer(message="...")
            found = re.search(r'message="((?:[^"\\]|\\.)*)"', text)
            if found:
                return found.group(1).replace("\\n", "\n").replace('\\"', '"')
            if text:
                return text
    return ""


result = st.session_state.get("result")
if result:
    answer = result["answer"]
    st.divider()
    if answer:
        message = answer["message"]
        if language(message) == "ar":  # Arabic reads right to left
            st.markdown('<style>.rtl{text-align:right} .rtl ul,.rtl ol{padding-left:0;padding-right:1.5em}</style>'
                        f'<div dir="rtl" class="rtl">\n\n{message}\n\n</div>', unsafe_allow_html=True)
        else:
            st.markdown(message)

        if answer.get("trip"):
            label = "Proposed trip" if answer["action"] == "propose" else "Closest option (over budget)"
            with st.container(border=True):
                st.caption(label)
                for line in trip_lines(answer["trip"]):
                    st.markdown(line)
        for h in answer.get("habits_used", []):
            st.caption(f"Habit used: {h.get('name')} ({h.get('reason')})")
    else:
        st.warning("The agent did not send its answer through the answer form (a known issue, about 5% of requests). "
                   "Its raw text is shown below.")
        st.markdown(last_text(result["transcript"]) or "_No text._")

    with st.expander(f"How the agent got there: {len(result['tool_calls'])} steps"):
        for i, c in enumerate(result["tool_calls"], 1):
            st.markdown(f"{i}. {step_label(c)} `{c['tool']}`")
        if result["purchase_attempts"]:
            st.markdown(f"⛔ Tried to book {result['purchase_attempts']} time(s); booking is disabled.")
    st.caption(f"{result['seconds']} s · ${result['cost_usd']:.4f} · model {MODEL}, prompt {PROMPT}")
