"""Web page to try the travel agent (Streamlit).

Run locally:   streamlit run app.py
Hosted on Streamlit Community Cloud. Two private settings ("secrets"):
    AI71_API_KEY = "..."     # the Anthropic API key (put a spending cap on it)
    APP_PASSWORD = "..."     # optional: asks for this password before showing the page

The page runs the frozen final version: Haiku 5.5 + prompt v2.
"""

import json
import os
import re
import unicodedata
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

HABIT = {  # shown in "Who is asking?"
    "nadia": "usually flies Air France", "hugo": "mixed habits (Air France and easyJet, Hilton and Marriott)",
    "tom": "usually flies easyJet", "sofia": "usually stays at Marriott", "lea": "usually stays at Marriott",
    "karim": "stayed at Hilton twice", "maxim": "no travel history", "ines": "no travel history",
}

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


# --- Customer card payments, in one line -------------------------------------
def history(user):
    """'Air France x4, easyJet x2' from the card payments."""
    counts = Counter(p["merchant"].title() for p in user["card_payments"])
    return ", ".join(f"{m} x{n}" for m, n in counts.most_common()) or "no travel payments"


# --- Main page -----------------------------------------------------------------
st.title("✈️ Travel agent")
with st.expander("About this prototype", expanded=True):
    st.markdown(f"""
A prototype of a travel assistant for a digital bank. Ask for a trip as a customer would:
the agent searches flights and hotels, checks the budget, uses the customer's card history as a hint,
and proposes one trip. **It never books.** Any language works.

**Small, made-up data set.** Destinations: {", ".join(world.HOTEL_CITIES)}.
Customers can also fly from {", ".join(c for c in world.FLIGHT_CITIES if c not in world.HOTEL_CITIES)}, but there are no hotels there.
Trips from 20 October 2026 to 10 January 2027 ("today" is 11 October 2026).

**Pick a customer** in "Who is asking?" below,
or choose "Me: create my profile" there to set your own city, airline and hotel brand.
Limit: {MAX_REQUESTS} requests per visit.
""")

def use_example(uid, text):
    # Runs before the page redraws, so it can still change the customer list and the request box
    st.session_state.user_id = uid
    st.session_state.chat = []
    st.session_state.chat_box = text  # fills the message box, so the request can be edited before sending


with st.expander("Example requests"):
    for uid, text in EXAMPLES:
        st.button(f"{world.USERS[uid]['name']}: {text}", key=text, on_click=use_example, args=(uid, text))

personas = [u for u in world.USERS if not u.startswith("me-")]
st.session_state.setdefault("user_id", personas[0])
user_id = st.selectbox("Who is asking?", ["me"] + personas, key="user_id",
                       format_func=lambda u: "Me: create my profile" if u == "me"
                       else f"{world.USERS[u]['name']} ({world.USERS[u]['home_city']})"
                       + (f" · {HABIT[u]}" if u in HABIT else ""),
                       help="Each customer has past card payments that the agent uses as a soft preference. "
                            "An explicit request always wins.")
if user_id == "me":
    with st.container(border=True):
        left, right = st.columns(2)
        name = left.text_input("Your first name", value="Alex")
        city = right.selectbox("You live in", world.FLIGHT_CITIES, index=world.FLIGHT_CITIES.index("Paris"))
        airline = left.selectbox("Airline you fly most", ["None"] + AIRLINES, index=1 + AIRLINES.index("Air France"))
        trips = right.slider("Round trips with it, last 12 months", 0, 6, 3, help="2 or more = strong habit")
        brand = left.selectbox("Hotel brand you stay with most", ["None"] + HOTEL_BRANDS, index=1)
        stays = right.slider("Stays with it, last 24 months", 0, 6, 2, help="3 or more = strong habit, 2 = tie-breaker")
    # One profile per browser session, so visitors don't overwrite each other
    st.session_state.setdefault("me_id", f"me-{uuid.uuid4().hex[:8]}")
    user_id = st.session_state.me_id
    world.USERS[user_id] = make_profile(name, city, None if airline == "None" else airline, trips,
                                        None if brand == "None" else brand, stays)
user = world.USERS[user_id]
st.caption(f"Lives in {user['home_city']} · Travel card payments: {history(user)}")

# A new customer starts a new conversation
if st.session_state.get("chat_user") != user_id:
    st.session_state.chat = []
    st.session_state.chat_user = user_id
chat = st.session_state.setdefault("chat", [])

def budget_from(request, travellers=1):
    """The budget in euros written in the request, or None. Only for the budget bar on the page."""
    text = "".join(str(unicodedata.digit(c)) if c.isdigit() else c for c in request)  # Arabic digits
    num = r"(\d+(?:[.,\s ]\d{3})*(?:[.,]\d+)?\s*k?)"
    cur = r"(?:euros?|eur|€|يورو)"
    found = re.findall(num + r"\s*" + cur, text, re.I) or re.findall(cur + r"\s*" + num, text, re.I) \
        or re.findall(r"(\d+(?:[.,]\d+)?\s*k)\b", text, re.I)
    if not found:
        return None
    raw = found[-1].strip().lower()
    k = raw.endswith("k")
    raw = raw.rstrip("k").strip()
    if re.fullmatch(r"\d+[.,]\d{1,2}", raw) and k:
        value = float(raw.replace(",", "."))
    else:
        value = float(re.sub(r"[.,\s ]", "", raw))
    value *= 1000 if k else 1
    if re.search(r"\b(each|per person|par personne|chacun|cada uno|por persona)\b", text, re.I):
        value *= travellers
    return value


def nice_date(iso):
    d = date.fromisoformat(iso)
    return f"{d:%a} {d.day} {d:%b}"


def trip_card(trip, action, habits, budget):
    """The trip as a card, rebuilt from the data (not from the agent's text)."""
    out = world.FLIGHTS_BY_ID.get(trip.get("outbound_flight_id"))
    ret = world.FLIGHTS_BY_ID.get(trip.get("return_flight_id"))
    hotel = world.HOTELS_BY_ID.get(trip.get("hotel_id"))
    travellers = trip.get("travellers", 1)
    total, problems = world.price_trip(trip.get("outbound_flight_id"), trip.get("return_flight_id"),
                                       trip.get("hotel_id"), trip.get("room_type"),
                                       trip.get("rooms", 1), travellers)
    with st.container(border=True):
        st.caption("PROPOSED TRIP" if action == "propose" else "CLOSEST OPTION (DOES NOT FIT)")
        if out:
            photo = f"assets/cities/{out['destination']}.jpg"
            if os.path.exists(photo):
                st.image(photo, use_container_width=True)
            st.subheader(f"{out['origin']} → {out['destination']}")
        st.markdown("**Flights**")
        flights = st.columns(2)
        for col, label, f in ((flights[0], "Departure", out), (flights[1], "Return", ret)):
            if f:
                stops = "Direct" if f["stops"] == 0 else f"{f['stops']} stop(s)"
                col.markdown(f"✈️ {label} · {nice_date(f['date'])}  \n"
                             f"{f['airline']}, {f['departure_time']} · {stops}  \n"
                             f"€{f['price_per_person_eur']} per person")
        if hotel:
            st.divider()
            st.markdown("**Hotel**")
            nights = ""
            if out and ret:
                n = (date.fromisoformat(ret["date"]) - date.fromisoformat(out["date"])).days
                nights = f" · {n} night{'s' if n > 1 else ''}"
            st.markdown(f"🏨 {hotel['name']} {'★' * hotel['stars']}  \n"
                        f"{hotel['area']} · {trip.get('rooms', 1)} × {trip.get('room_type')} room{nights}")
        if total is not None:
            st.divider()
            st.markdown("**Budget**")
            st.markdown(f"### €{total:,.0f}")
            st.caption(f"Total for {travellers} traveller{'s' if travellers > 1 else ''}, checked against the data")
            if budget:
                if total <= budget:
                    st.progress(total / budget, text=f"€{total:,.0f} of your €{budget:,.0f} budget · €{budget - total:,.0f} left")
                else:
                    st.progress(1.0, text=f"⚠️ €{total - budget:,.0f} over your €{budget:,.0f} budget")
        if habits:
            st.divider()
            st.markdown("**Why this choice**")
        for h in habits:
            icon = "✈️" if h.get("kind") == "airline" else "🏨"
            st.markdown(f":blue-badge[{icon} Your habit: {h.get('name')}] {h.get('reason')}")
        for p in problems:
            st.warning(p)


def money(values):
    return f"from €{min(values):,.0f}" if values else ""


def step_line(name, args, result):
    """One plain-language line per tool call, with what it found."""
    try:
        r = json.loads(result)
    except (TypeError, ValueError):
        r = {}
    if r.get("error") and name != "book_trip":
        return f"⚠️ {name.replace('_', ' ').capitalize()}: {r['error']}"
    if name == "get_user_profile":
        return f"👤 Read the profile: {r.get('name')}, lives in {r.get('home_city')}"
    if name == "get_card_payments":
        pays = r.get("payments", [])
        top = Counter(p["merchant"].title() for p in pays).most_common(3)
        found = ", ".join(f"{m} x{n}" for m, n in top)
        return f"💳 Read {len(pays)} travel card payments" + (f": {found}" if found else " (none)")
    if name == "search_flights":
        flights = r.get("flights", [])
        when = nice_date(args["date"]) if args.get("date") else ""
        line = f"✈️ Searched flights {args.get('origin')} → {args.get('destination')}, {when}: "
        if not flights:
            return line + "none found"
        airlines = ", ".join(sorted({f["airline"] for f in flights}))
        return line + f"{len(flights)} found ({airlines}), {money([f['price_per_person_eur'] for f in flights])} per person"
    if name == "search_hotels":
        hotels = r.get("hotels", [])
        nights = hotels[0]["nights"] if hotels else 0
        prices = [room["price_per_night_eur"] for h in hotels for room in h["rooms"]]
        return (f"🏨 Searched hotels in {args.get('city')}, {nights} night{'s' if nights != 1 else ''}: "
                f"{len(hotels)} found, {money(prices)} a night")
    if name == "book_trip":
        return "⛔ Tried to book: blocked, booking is disabled"
    if name == "submit_answer":
        return {"propose": "✅ Sent the proposal", "nothing_fits": "✅ Said nothing fits, with the closest option",
                "ask": "❓ Asked the customer a question"}.get(args.get("action"), "✅ Sent the answer")
    return name


def steps_from(transcript):
    """(name, input, result) for every tool call, read back from a saved transcript."""
    calls, steps = {}, []
    for m in transcript:
        if isinstance(m["content"], str):
            continue
        for c in m["content"]:
            if c.get("type") == "tool_use":
                calls[c["id"]] = c
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                call = calls[c["tool_use_id"]]
                steps.append((call["name"], call["input"], c.get("content")))
    return steps


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


def show_answer(turn):
    """The agent's side of one turn: steps, trip card, message."""
    result = turn["result"]
    answer = result["answer"]
    steps = steps_from(result["transcript"])
    with st.status(f"Worked in {len(steps)} step{'s' if len(steps) != 1 else ''}, {result['seconds']} s", state="complete", expanded=False):
        for step in steps:
            st.write(step_line(*step))
        if turn["sent"] != turn["text"]:
            st.caption("The agent has no memory, so the page sent everything you wrote as one request:")
            st.code(turn["sent"], language=None, wrap_lines=True)
    if answer:
        if answer.get("trip"):  # the card first: the answer at a glance, details in the text below
            trip_card(answer["trip"], answer["action"], answer.get("habits_used", []),
                      budget_from(turn["sent"], answer["trip"].get("travellers", 1)))
        message = answer["message"]
        # With a trip card the text mostly repeats it: keep it folded. Questions and "nothing fits" stay open.
        with (st.expander("Read the agent's full message") if answer.get("trip") else st.container()):
            if language(message) == "ar":  # Arabic reads right to left
                st.markdown('<style>.rtl{text-align:right} .rtl ul,.rtl ol{padding-left:0;padding-right:1.5em}</style>'
                            f'<div dir="rtl" class="rtl">\n\n{message}\n\n</div>', unsafe_allow_html=True)
            else:
                st.markdown(message)
    else:
        st.warning("The agent did not send its answer through the answer form (a known issue, about 5% of requests). "
                   "Its raw text is shown below.")
        st.markdown(last_text(result["transcript"]) or "_No text._")
    st.caption(f"{result['seconds']} s · ${result['cost_usd']:.4f} · model {MODEL}, prompt {PROMPT}")


for turn in chat:
    with st.chat_message("user"):
        st.markdown(turn["text"])
    with st.chat_message("assistant"):
        show_answer(turn)

if chat:
    st.button("New trip", on_click=lambda: st.session_state.update(chat=[]))

used = st.session_state.get("used", 0)
if used >= MAX_REQUESTS:
    st.info("Request limit reached for this session.")
text = st.chat_input("Reply to the agent..." if chat else "Ask for a trip, e.g. Rome from 27 to 29 November, 1000 euros",
                      disabled=used >= MAX_REQUESTS, key="chat_box")

if text:
    if not key:
        st.error("No API key configured.")
        st.stop()
    st.session_state.used = used + 1
    # The agent reads one request and has no memory: send the customer's earlier messages along with the new one
    sent = "\n".join([t["text"] for t in chat] + [text])
    with st.chat_message("user"):
        st.markdown(text)
    with st.chat_message("assistant"):
        with st.status("The agent is working...", expanded=True) as live:
            try:
                result = run_agent(
                    user_id, sent, model=MODEL, system_prompt=PROMPTS[PROMPT], client=make_client(),
                    on_step=lambda name, args, res: live.write(step_line(name, args, res)))
            except Exception as e:
                live.update(label="Something went wrong", state="error")
                st.error(f"Something went wrong: {e}")
                st.stop()
    chat.append({"text": text, "sent": sent, "result": result})
    st.rerun()  # redraw with the steps folded and the trip card on top
