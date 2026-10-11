"""Web page to try the travel agent (Streamlit).

Run locally:   streamlit run app.py
Hosted on Streamlit Community Cloud. Two private settings ("secrets"):
    AI71_API_KEY = "..."     # the Anthropic API key (put a spending cap on it)
    APP_PASSWORD = "..."     # optional: asks for this password before showing the page

The page runs the frozen final version: Haiku 5.5 + prompt v2.
"""

import os
import re
from collections import Counter

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


# --- Sidebar: who is asking, and what the fake world contains ----------------
def history(user):
    """'Air France x4, easyJet x2' from the card payments."""
    counts = Counter(p["merchant"].title() for p in user["card_payments"])
    return ", ".join(f"{m} x{n}" for m, n in counts.most_common()) or "no travel payments"


with st.sidebar:
    st.header("Customer")
    ids = list(world.USERS)
    user_id = st.selectbox("Who is asking?", ids, key="user_id",
                           format_func=lambda u: f"{world.USERS[u]['name']} ({world.USERS[u]['home_city']})")
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
st.write("Ask for a trip as a bank customer would. The agent searches flights and hotels, "
         "checks your budget, uses your card history as a hint, and proposes a trip. "
         "It never books. Any language works.")

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
