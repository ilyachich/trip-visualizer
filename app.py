"""
Vacation Trip Planner — Streamlit web app (dark theme)
"""

import os
import re
import contextlib
import io
import time as _time
from datetime import datetime as _dt

import streamlit as st
import streamlit.components.v1 as components
from groq import Groq

from trip_visualizer import (
    NATURE_PLANNER_SYSTEM_PROMPT,
    DAY_COLORS,
    TYPE_EMOJI,
    TRANSPORT_MODE_EMOJI,
    parse_trip,
    geocode_trip,
    calculate_routes,
    fetch_wiki_images,
    build_map,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Vacation Trip Planner",
    page_icon="🌍",
    layout="wide",
)

API_KEY = os.environ.get("GROQ_API_KEY", "")

# ---------------------------------------------------------------------------
# Dark theme CSS
# ---------------------------------------------------------------------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Base ── */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="block-container"] {
    background-color: #080F1E !important;
    color: #CBD5E1 !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}
[data-testid="stHeader"] { background: transparent !important; }
#MainMenu, footer, header { visibility: hidden; }

/* ── Typography ── */
p, span, div, li, label,
.stMarkdown, [data-testid="stMarkdown"] * {
    color: #CBD5E1 !important;
    font-family: 'Inter', system-ui, sans-serif !important;
}
h1, h2, h3, h4, h5 { color: #F0F9FF !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background-color: #0F1D35 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 12px !important;
    gap: 4px; padding: 5px;
    margin-bottom: 1rem !important;
}
.stTabs [data-baseweb="tab"] {
    color: #64748B !important;
    border-radius: 8px !important;
    padding: 10px 28px;
    font-size: 1em; font-weight: 500;
    cursor: pointer !important;
    transition: all .2s ease;
    border-bottom: none !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #CBD5E1 !important;
    background: #162844 !important;
}
.stTabs [aria-selected="true"] {
    color: #F0F9FF !important;
    background: linear-gradient(135deg, #0EA5E9, #0891B2) !important;
    border-bottom: none !important;
    box-shadow: 0 2px 14px rgba(14,165,233,.35) !important;
}

/* ── Text inputs & textarea ── */
input[type="text"], textarea,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background-color: #162844 !important;
    color: #CBD5E1 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
}
input:focus, textarea:focus {
    border-color: #38BDF8 !important;
    box-shadow: 0 0 0 3px rgba(56,189,248,.15) !important;
    outline: none !important;
}

/* ── Selectbox ── */
[data-baseweb="select"] > div:first-child {
    background-color: #162844 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
    cursor: pointer !important;
}
[data-baseweb="select"] svg { fill: #64748B !important; }

/* ── Dropdown popup ── */
[data-baseweb="popover"],
[data-baseweb="menu"],
[role="listbox"] {
    background-color: #162844 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
}
[role="option"] {
    background-color: #162844 !important;
    color: #CBD5E1 !important;
    cursor: pointer !important;
    padding: 8px 12px !important;
}
[role="option"]:hover,
[aria-selected="true"][role="option"] {
    background-color: #1A3255 !important;
    color: #38BDF8 !important;
}

/* ── Multiselect tags ── */
[data-baseweb="tag"] {
    background-color: #0C2D4E !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 6px !important;
    cursor: default !important;
}
[data-baseweb="tag"] span { color: #7DD3FC !important; }
[data-baseweb="tag"] [role="presentation"] { cursor: pointer !important; }

/* ── Multiselect input ── */
[data-baseweb="multi-select"] {
    background-color: #162844 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
    cursor: pointer !important;
}

/* ── Radio buttons — equal-width card style ── */
[data-testid="stRadio"] > div {
    display: flex; flex-wrap: wrap; gap: 8px;
}
[data-testid="stRadio"] label {
    flex: 1 !important;
    min-width: 120px !important;
    text-align: center !important;
    justify-content: center !important;
    background-color: #0F1D35 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
    padding: 9px 16px !important;
    color: #CBD5E1 !important;
    cursor: pointer !important;
    transition: background .15s, border-color .15s;
    margin: 0 !important;
}
[data-testid="stRadio"] label:hover {
    background-color: #162844 !important;
    border-color: #38BDF8 !important;
}
[data-testid="stRadio"] label:has(input:checked) {
    background-color: #0C2D4E !important;
    border-color: #38BDF8 !important;
    color: #7DD3FC !important;
}

/* ── Select slider ── */
[data-testid="stSlider"] * { cursor: pointer !important; }
[data-testid="stSlider"] [role="slider"] {
    background-color: #38BDF8 !important;
}
[data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSlider"] [data-testid="stTickBarMax"] {
    color: #64748B !important;
}
[data-testid="stSlider"] [data-testid="stSliderThumb"] {
    background-color: #38BDF8 !important;
}

/* ── Cursor pointer globally ── */
button, [role="button"],
[data-baseweb="select"], .stMultiSelect,
[data-testid="stRadio"] *, [data-testid="stCheckbox"] * {
    cursor: pointer !important;
}

/* ── Submit / Generate button (orange CTA) ── */
div[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, #C2570C, #F97316) !important;
    color: #fff !important; border: none !important;
    border-radius: 12px !important;
    font-size: 1.1em !important; font-weight: 700 !important;
    padding: 0.85em 2em !important;
    box-shadow: 0 4px 20px rgba(249,115,22,.4) !important;
    transition: transform .15s, box-shadow .15s !important;
    cursor: pointer !important;
    letter-spacing: 0.3px !important;
}
div[data-testid="stFormSubmitButton"] > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(249,115,22,.55) !important;
}

/* ── Download button ── */
div[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #0284C7, #0EA5E9) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    box-shadow: 0 4px 14px rgba(14,165,233,.35) !important;
    cursor: pointer !important;
    transition: transform .15s, box-shadow .15s !important;
}
div[data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(14,165,233,.5) !important;
}

/* ── Secondary / plain button ── */
button[kind="secondary"] {
    background: #0F1D35 !important;
    color: #CBD5E1 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 8px !important;
    transition: all .15s !important;
}
button[kind="secondary"]:hover {
    background: #162844 !important;
    border-color: #64748B !important;
}

/* ── Primary button (non-form) ── */
button[kind="primary"] {
    background: linear-gradient(135deg, #C2570C, #F97316) !important;
    color: #fff !important; border: none !important;
    border-radius: 10px !important; font-weight: 600 !important;
    box-shadow: 0 4px 16px rgba(249,115,22,.35) !important;
    cursor: pointer !important;
    transition: transform .15s, box-shadow .15s !important;
}
button[kind="primary"]:hover {
    transform: translateY(-1px) !important;
}

/* ── Divider ── */
hr { border-color: #1F3D5C !important; }

/* ── Container border ── */
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-color: #1F3D5C !important;
    border-radius: 12px !important;
    background-color: #0F1D35 !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background-color: #0F1D35 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 10px !important;
}
details summary { cursor: pointer !important; color: #64748B !important; }
details[open] summary { color: #38BDF8 !important; }

/* ── Status widget ── */
[data-testid="stStatusWidget"],
[data-testid="stStatus"] {
    background-color: #0F1D35 !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 12px !important;
}

/* ── Alert ── */
[data-testid="stAlert"] {
    background-color: #0F1D35 !important;
    border-radius: 10px !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: #38BDF8 !important; }

/* ── Form card ── */
[data-testid="stForm"] {
    background: rgba(15,29,53,0.55) !important;
    border: 1px solid #1F3D5C !important;
    border-radius: 16px !important;
    padding: 1.5rem 2rem !important;
}

/* ── Widget question labels ── */
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] label {
    color: #94BDDB !important;
    font-weight: 600 !important;
    font-size: 0.87em !important;
    letter-spacing: 0.2px !important;
}

/* ── Slider filled track ── */
[data-testid="stSlider"] [data-baseweb="slider-track"] > div:last-child {
    background: #0EA5E9 !important;
}

/* ── Intro paragraph ── */
.trip-intro { color: #8BBBDB !important; margin-bottom: 1.2rem; }

/* ── Animations ── */
@keyframes aurora {
    0%   { transform: scale(1) translate(0, 0); }
    50%  { transform: scale(1.06) translate(-2%, 2%); }
    100% { transform: scale(1) translate(0, 0); }
}
@keyframes fadeUp {
    from { opacity: 0; transform: translateY(14px); }
    to   { opacity: 1; transform: translateY(0); }
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_resource
def _groq_client() -> Groq:
    return Groq(api_key=API_KEY)


def groq_chat(messages: list[dict], max_tokens: int = 4096) -> str:
    resp = _groq_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def build_map_html(text: str, status_widget=None, t0: float | None = None) -> tuple[str, dict]:
    """Run full pipeline silently; status_widget is optional (legacy)."""
    with contextlib.redirect_stderr(io.StringIO()):
        trip_data = parse_trip(text, api_key=API_KEY)
        geocode_trip(trip_data)
        calculate_routes(trip_data)
        fetch_wiki_images(trip_data)
        m = build_map(trip_data)
    return m.get_root().render(), trip_data


# Section header config  {key: (hex_color, emoji, label)}
_SEC = {
    "destination": ("#388bfd", "📍", "Destination & Timing"),
    "travelers":   ("#3fb950", "👥", "Travelers"),
    "style":       ("#bc8cff", "🎯", "Trip Style & Pace"),
    "budget":      ("#ffa657", "💰", "Budget & Accommodation"),
    "transport":   ("#39d4c5", "🚗", "Getting Around"),
    "nature":      ("#56d364", "🏔️", "Nature & Activities"),
    "food":        ("#ff7b72", "🍽️", "Food & Dining"),
    "other":       ("#8b949e", "✏️", "Anything Else?"),
}

def section(key: str) -> None:
    c, icon, title = _SEC[key]
    st.markdown(
        f"""<div style="background:linear-gradient(90deg,{c}22,transparent);
            border-left:4px solid {c};border-radius:0 10px 10px 0;
            padding:10px 18px;margin:24px 0 12px 0">
            <span style="font-size:1.1em;font-weight:700;color:{c}">
                {icon}&nbsp;&nbsp;{title}
            </span></div>""",
        unsafe_allow_html=True,
    )


def _q(label: str) -> str:
    """Wrap question label in muted-grey style."""
    return f'<span style="color:#8b949e;font-size:0.82em;font-weight:600;letter-spacing:.4px;text-transform:uppercase">{label}</span>'


def prefs_to_prompt(p: dict) -> str:
    lines = ["Please generate a full detailed trip itinerary based on these preferences:\n"]
    if p.get("destination"):
        lines.append(f"Destination / region: {p['destination']}")
    if p.get("trip_start_city"):
        lines.append(f"Trip starts in: {p['trip_start_city']}")
    if p.get("trip_end_city"):
        lines.append(f"Trip ends in: {p['trip_end_city']} (one-way — do NOT return to start)")
    else:
        lines.append("Trip routing: round trip — the last day should return to the starting city")
    month = p.get("month", "")
    if "flexible" not in month.lower():
        timing = month
        if p.get("year", "Flexible") != "Flexible":
            timing += f" {p['year']}"
        lines.append(f"Travel timing: {timing}")
    lines.append(f"Duration: {p['duration']} days")
    lines.append(f"Group: {p['group_size']} — {p['group_type']}")
    if p.get("trip_type"):
        lines.append(f"Trip focus: {', '.join(p['trip_type'])}")
    lines.append(f"Activity level: {p['activity_level']}")
    lines.append(f"Preferred pace: {p['pace']}")
    lines.append(f"Budget: {p['budget']}")
    if p.get("accommodation"):
        lines.append(f"Accommodation: {', '.join(p['accommodation'])}")
    lines.append(f"Main transport: {p['transport']}")
    lines.append(f"Max driving per day: {p['max_drive']}")
    if p.get("nature_prefs"):
        lines.append(f"Nature interests: {', '.join(p['nature_prefs'])}")
    if p.get("activities"):
        lines.append(f"Must-have activities: {', '.join(p['activities'])}")
    lines.append(f"Place type preference: {p['hidden_vs_popular']}")
    if p.get("food_prefs"):
        lines.append(f"Food preferences: {', '.join(p['food_prefs'])}")
    lines.append(f"Dining style: {p['dining_style']}")
    if p.get("special"):
        lines.append(f"Special requirements: {p['special']}")
    lines.append(
        "\nGenerate the full itinerary now — no clarifying questions. "
        "Use Day-by-Day sections, real geocodable place names, hotel check-in/check-out days."
    )
    return "\n".join(lines)


def reset_planner() -> None:
    st.session_state.plan_stage = "form"
    for k in ("plan_itinerary", "plan_map_html", "plan_trip_data"):
        st.session_state.pop(k, None)


def render_colorized_itinerary(text: str) -> None:
    """Render itinerary with day headers color-coded to match the map legend."""
    day_re = re.compile(
        r'(?m)^(?:#{1,3}\s*\*{0,2})((?:Day|DAY)\s+\d+[^\n]*)(?:\*{0,2})\s*$'
    )
    matches = list(day_re.finditer(text))
    if not matches:
        st.markdown(text)
        return
    pre = text[:matches[0].start()].strip()
    if pre:
        st.markdown(pre)
    for i, m in enumerate(matches):
        title = re.sub(r'\*+', '', m.group(1)).strip()
        day_num_m = re.search(r'\d+', title)
        day_num = int(day_num_m.group()) if day_num_m else (i + 1)
        color = DAY_COLORS[(day_num - 1) % len(DAY_COLORS)]
        st.markdown(
            f"""<div style="background:{color};color:white;
                padding:8px 16px;border-radius:6px;
                font-weight:700;font-size:1.05em;margin:20px 0 8px 0">
                {title}
            </div>""",
            unsafe_allow_html=True,
        )
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            st.markdown(body)


def render_structured_itinerary(trip_data: dict) -> None:
    """Render parsed trip data in the same visual style as the map's itinerary panel."""
    # ── Accommodations ──────────────────────────────────────────────────────
    accs = trip_data.get("accommodations", [])
    if accs:
        st.markdown(
            "<div style='font-weight:700;font-size:.95em;color:#94BDDB;"
            "padding:6px 0;border-bottom:1px solid #1F3D5C;margin-bottom:10px'>"
            "🏨 Accommodations</div>",
            unsafe_allow_html=True,
        )
        for acc in accs:
            stars = int(acc.get("stars") or 0)
            stars_s = "★" * stars if stars else ""
            ci = acc.get("check_in_day", "?")
            co = acc.get("check_out_day", "?")
            amenities = acc.get("amenities") or ""
            st.markdown(f"""
            <div style="background:rgba(15,29,53,0.7);border:1px solid #1F3D5C;
                border-radius:8px;padding:10px 14px;margin-bottom:8px">
                <div style="font-weight:700">🏨 {acc['name']}
                    {'<span style="color:#f0a500;margin-left:5px">' + stars_s + '</span>' if stars_s else ''}
                </div>
                <div style="font-size:.82em;color:#64748B;margin-top:2px">
                    Check-in Day {ci} · Check-out Day {co}
                </div>
                <div style="font-size:.88em;color:#94BDDB;margin-top:3px">
                    {acc.get('description', '')}
                </div>
                {'<div style="font-size:.78em;color:#64748B;margin-top:2px">🏷 ' + amenities + '</div>' if amenities else ''}
            </div>""", unsafe_allow_html=True)

    # ── Days ────────────────────────────────────────────────────────────────
    for i, day in enumerate(trip_data.get("days", [])):
        color     = DAY_COLORS[i % len(DAY_COLORS)]
        day_label = day.get("label") or f"Day {day['day_number']}"
        date_s    = day.get("date") or ""

        # Solid colored header — same style as map panel
        st.markdown(f"""
        <div style="background:{color};color:white;padding:8px 16px;
            border-radius:6px;font-weight:700;font-size:1.05em;margin:20px 0 8px 0">
            {day_label}
            {'<span style="opacity:.8;font-size:.85em;margin-left:8px">· ' + date_s + '</span>' if date_s else ''}
        </div>""", unsafe_allow_html=True)

        stop_num = 0
        for loc in sorted(day.get("locations", []), key=lambda x: x.get("order", 99)):
            loc_type = loc.get("type", "default")
            emoji    = TYPE_EMOJI.get(loc_type, TYPE_EMOJI["default"])
            if loc_type == "transport":
                mode  = (loc.get("transport_mode") or "train").lower()
                emoji = TRANSPORT_MODE_EMOJI.get(mode, "🚆")

            is_hotel = loc_type == "hotel"
            if not is_hotel:
                stop_num += 1
                badge = (
                    f'<span style="background:white;color:{color};'
                    f'border:2px solid {color};border-radius:50%;'
                    f'padding:1px 5px;font-size:.72em;font-weight:700;'
                    f'margin-right:5px;vertical-align:middle">{stop_num}</span>'
                )
            else:
                badge = ""

            highlights = loc.get("highlights") or ""
            tips       = loc.get("tips")       or ""
            cuisine    = loc.get("cuisine")    or ""
            price      = loc.get("price_range") or ""
            route      = loc.get("_route_to_next")

            cuisine_html = ""
            if cuisine:
                cuisine_html = f'<div style="font-size:.78em;color:#94BDDB;margin-top:2px">🍴 {cuisine}'
                if price:
                    cuisine_html += f" · {price}"
                cuisine_html += "</div>"

            route_html = ""
            if route:
                km     = route["km"]
                mins   = route["drive_mins"]
                next_n = route.get("next_name", "next stop")
                travel = (f"🚶 {round(km/0.08)} min walk" if km < 1.5
                          else f"🚗 {mins} min")
                route_html = (
                    f'<div style="font-size:.78em;color:#64748B;margin-top:4px">'
                    f'→ {next_n}: {km} km · {travel}</div>'
                )

            st.markdown(f"""
            <div style="padding:8px 12px 8px 14px;border-left:4px solid {color};
                background:rgba(15,29,53,0.5);border-radius:0 8px 8px 0;
                margin-bottom:6px">
                <div style="font-weight:600">{badge}{emoji} {loc['name']}</div>
                <div style="font-size:.85em;color:#94BDDB;margin-top:2px">
                    {loc.get('description', '')}
                </div>
                {'<div style="font-size:.78em;color:#34D399;margin-top:3px">✨ ' + highlights + '</div>' if highlights else ''}
                {'<div style="font-size:.78em;color:#38BDF8;margin-top:2px">💡 ' + tips + '</div>' if tips else ''}
                {cuisine_html}
                {route_html}
            </div>""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Hero
# ---------------------------------------------------------------------------

st.markdown("""
<div style="
    position:relative;
    background:linear-gradient(135deg,#04080F 0%,#0A1628 30%,#0F2340 65%,#0B1E10 100%);
    border:1px solid #1E3A5F;
    border-radius:20px;
    padding:2.8rem 3rem 2.4rem;
    margin-bottom:1.6rem;
    overflow:hidden;
    animation:fadeUp 0.5s ease;
">
    <!-- grid pattern -->
    <div style="position:absolute;inset:0;
        background-image:linear-gradient(rgba(14,165,233,0.04) 1px,transparent 1px),
                         linear-gradient(90deg,rgba(14,165,233,0.04) 1px,transparent 1px);
        background-size:36px 36px;border-radius:20px;pointer-events:none;">
    </div>
    <!-- glow orbs -->
    <div style="position:absolute;top:-30%;left:8%;width:420px;height:320px;
        background:radial-gradient(ellipse,rgba(14,165,233,0.09) 0%,transparent 70%);
        animation:aurora 10s ease-in-out infinite;pointer-events:none;">
    </div>
    <div style="position:absolute;bottom:-20%;right:12%;width:300px;height:260px;
        background:radial-gradient(ellipse,rgba(16,185,129,0.07) 0%,transparent 70%);
        pointer-events:none;">
    </div>
    <!-- content -->
    <div style="position:relative;z-index:1;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:1rem;">
            <span style="background:rgba(14,165,233,0.12);border:1px solid rgba(14,165,233,0.28);
                color:#38BDF8;border-radius:100px;padding:4px 14px;
                font-size:0.78em;font-weight:600;letter-spacing:0.2px;">
                ✦ AI-Powered
            </span>
            <span style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.25);
                color:#34D399;border-radius:100px;padding:4px 14px;
                font-size:0.78em;font-weight:600;">
                100% Free
            </span>
            <span style="background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.25);
                color:#FB923C;border-radius:100px;padding:4px 14px;
                font-size:0.78em;font-weight:600;">
                No Signup Needed
            </span>
        </div>
        <div style="font-size:2.4em;font-weight:800;color:#F0F9FF;line-height:1.15;
                    letter-spacing:-0.5px;margin-bottom:0.5rem;">
            Vacation Trip Planner
        </div>
        <div style="font-size:1em;color:#8BBBDB;line-height:1.65;
                    margin-bottom:1.3rem;max-width:600px;">
            Fill in your travel preferences and get a personalised AI itinerary
            with a colour-coded interactive map — ready to download and use offline.
        </div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
                color:#8BBBDB;border-radius:8px;padding:6px 14px;font-size:0.84em;font-weight:500;">
                🗺️ Interactive Map
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
                color:#8BBBDB;border-radius:8px;padding:6px 14px;font-size:0.84em;font-weight:500;">
                🏨 Hotel Routing
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
                color:#8BBBDB;border-radius:8px;padding:6px 14px;font-size:0.84em;font-weight:500;">
                📸 Place Photos
            </div>
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
                color:#8BBBDB;border-radius:8px;padding:6px 14px;font-size:0.84em;font-weight:500;">
                ⬇️ Download Offline
            </div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

if not API_KEY:
    st.error("⚠️ GROQ_API_KEY not set. Add it to Streamlit secrets: GROQ_API_KEY = \"your-key\"")
    st.stop()

# ===========================================================================
# Trip Planner — single-page flow
# ===========================================================================

if "plan_stage" not in st.session_state:
    st.session_state.plan_stage = "form"

# ── STAGE: form ────────────────────────────────────────────────────────────
if st.session_state.plan_stage == "form":

    st.markdown(
        "<p class='trip-intro'>Fill in your preferences — the AI will create a "
        "personalised itinerary with a day-by-day colour-coded map.</p>",
        unsafe_allow_html=True,
    )

    with st.form("trip_form", border=False):

        # ── Destination & Timing ─────────────────────────────────────────
        section("destination")
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            destination = st.text_input(
                "1. Region / country to explore ✱",
                placeholder="e.g. Slovenia, Austrian Alps, Norwegian fjords…",
            )
        with col2:
            month = st.selectbox("2. Travel month", [
                "January","February","March","April","May","June",
                "July","August","September","October","November",
                "December","Flexible / Not sure yet",
            ], index=_dt.now().month - 1)
        with col3:
            _yr_opts = ["2025","2026","2027","Flexible"]
            _yr_now  = str(_dt.now().year)
            year = st.selectbox("Year", _yr_opts,
                                index=_yr_opts.index(_yr_now) if _yr_now in _yr_opts else 1)

        col1, col2 = st.columns(2)
        with col1:
            trip_start_city = st.text_input(
                "3. Trip starts in ✱",
                placeholder="e.g. Ljubljana, Vienna, Oslo…",
            )
        with col2:
            trip_end_city = st.text_input(
                "4. Trip ends in  (leave blank for a round trip)",
                placeholder="e.g. Dubrovnik, Split… optional for one-way trips",
            )

        duration = st.select_slider(
            "5. Trip duration (days)",
            options=list(range(3, 15)),
            value=7,
        )
        st.markdown(
            '<div style="display:flex;justify-content:space-between;padding:0 6px;'
            'margin:-10px 0 14px 0;color:#64748B;font-size:.7em;pointer-events:none">'
            + "".join(f"<span>{n}</span>" for n in range(3, 15))
            + "</div>",
            unsafe_allow_html=True,
        )

        # ── Travelers ───────────────────────────────────────────────────
        section("travelers")
        col1, col2 = st.columns(2)
        with col1:
            group_size = st.selectbox("6. How many people?", [
                "1 — Solo traveler","2 — Couple",
                "3–4 people","5–8 people","9 or more",
            ])
        with col2:
            group_type = st.selectbox("7. Who's traveling?", [
                "Solo traveler",
                "Couple (no children)",
                "Family with young children (under 12)",
                "Family with teenagers",
                "Group of friends",
                "Multi-generation family",
            ])

        # ── Trip Style & Pace ────────────────────────────────────────────
        section("style")
        trip_type = st.multiselect(
            "8. Type of trip (select all that apply)",
            [
                "🏔️ Mountains & valleys","🏖️ Beaches & coastline",
                "🌊 Lakes & rivers","🌲 Forests & trails",
                "🦅 Wildlife & national parks","🏛️ Culture & local life",
                "🚵 Adventure sports","📷 Photography & scenic drives",
                "🧘 Relaxation & wellness",
            ],
            default=["🏔️ Mountains & valleys"],
        )
        activity_level = st.select_slider(
            "9. Activity level",
            options=["Very relaxed","Mostly relaxed","Moderate",
                     "Active","Very active / challenging"],
            value="Moderate",
        )
        st.markdown(
            '<div style="display:flex;justify-content:space-between;padding:0 6px;'
            'margin:-10px 0 14px 0;color:#64748B;font-size:.7em;pointer-events:none">'
            "<span>Very relaxed</span><span>Mostly relaxed</span>"
            "<span>Moderate</span><span>Active</span><span>Very active</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        pace = st.radio(
            "10. Preferred pace",
            ["🐢 Slow — fewer stops, more time per place",
             "⚖️ Balanced — a good mix of depth & variety",
             "⚡ Fast — visit as many places as possible"],
            horizontal=True,
        )

        # ── Budget & Accommodation ───────────────────────────────────────
        section("budget")
        col1, col2 = st.columns(2)
        with col1:
            budget = st.selectbox("11. Budget per person per day", [
                "💚 Budget — under $50 / day",
                "💛 Mid-range — $50–$150 / day",
                "🟠 Comfort — $150–$300 / day",
                "🔴 Luxury — $300+ / day",
            ])
        with col2:
            accommodation = st.multiselect(
                "12. Accommodation type",
                [
                    "🏕️ Camping / glamping","🛏️ Hostel",
                    "🏡 Guesthouse / B&B","🏨 3-star hotel",
                    "🏨 4-star hotel","🏨 5-star / luxury hotel",
                    "✨ Boutique / unique stays",
                    "⛺ Mountain hut / refuge",
                    "🏠 Vacation rental (Airbnb-style)",
                ],
                default=["🏨 3-star hotel"],
            )

        # ── Getting Around ───────────────────────────────────────────────
        section("transport")
        col1, col2 = st.columns(2)
        with col1:
            transport = st.selectbox("13. Main transport mode", [
                "🚗 Rental car (most flexibility)",
                "🚌 Public transport (trains & buses)",
                "🔀 Mix of both",
                "🚐 Private transfers / guided tours",
                "🚲 Cycling",
                "❓ Not decided yet",
            ])
        with col2:
            max_drive = st.select_slider(
                "14. Maximum driving per day",
                options=["Under 30 minutes","30–60 minutes","1–1.5 hours",
                         "1.5–2 hours","2+ hours (fine with long drives)"],
                value="1–1.5 hours",
            )
            st.markdown(
                '<div style="display:flex;justify-content:space-between;padding:0 6px;'
                'margin:-10px 0 14px 0;color:#64748B;font-size:.7em;pointer-events:none">'
                "<span>&lt;30 min</span><span>30–60 min</span>"
                "<span>1–1.5 h</span><span>1.5–2 h</span><span>2+ h</span>"
                "</div>",
                unsafe_allow_html=True,
            )

        # ── Nature & Activities ──────────────────────────────────────────
        section("nature")
        col1, col2 = st.columns(2)
        with col1:
            nature_prefs = st.multiselect(
                "15. Nature interests",
                [
                    "🗻 Mountain peaks & ridges","💎 Alpine lakes",
                    "💧 Waterfalls","🌲 Forests & hiking trails",
                    "🏞️ Canyons & gorges","🌊 Beaches & coastline",
                    "🦇 Caves & underground","♨️ Hot springs & geothermal",
                    "🦁 Wildlife & bird watching",
                    "🌅 Scenic viewpoints & panoramas",
                ],
            )
        with col2:
            activities = st.multiselect(
                "16. Must-have activities",
                [
                    "🥾 Day hiking","🎒 Multi-day trekking",
                    "🏊 Swimming in nature","🚴 Cycling / mountain biking",
                    "🛶 Kayaking / rafting / canoeing",
                    "🧗 Rock climbing / via ferrata",
                    "⛷️ Skiing / snowboarding","🦉 Wildlife watching",
                    "📸 Photography tours","🍷 Wine / food tasting",
                    "🏘️ Local markets & villages","⛵ Boat trips",
                    "🪂 Paragliding / zip-line",
                ],
            )
        hidden_vs_popular = st.radio(
            "17. What type of places do you prefer?",
            ["🔍 Hidden gems — off the beaten path",
             "⚖️ Mix — some popular, some hidden",
             "⭐ Popular highlights — classic must-sees"],
            horizontal=True,
        )

        # ── Food & Dining ────────────────────────────────────────────────
        section("food")
        col1, col2 = st.columns(2)
        with col1:
            food_prefs = st.multiselect(
                "18. Food preferences",
                [
                    "🍲 Local & traditional cuisine",
                    "🌍 International / familiar food",
                    "🥗 Vegetarian / vegan","🐟 Seafood",
                    "🌮 Street food & markets","🍽️ Fine dining",
                    "🧺 Picnics & self-catering",
                    "🌿 Farm-to-table / organic",
                ],
                default=["🍲 Local & traditional cuisine"],
            )
        with col2:
            dining_style = st.selectbox("19. Dining style", [
                "Local small restaurants (authentic, affordable)",
                "Mix of local and mid-range",
                "Comfortable, reliable restaurants",
                "High-end / fine dining",
            ])

        # ── Anything Else? ───────────────────────────────────────────────
        section("other")
        special = st.text_area(
            "20. Special requirements or must-see places (optional)",
            placeholder=(
                "e.g. We travel with a dog  ·  Wheelchair accessible  ·  "
                "Must include Lake Bled  ·  My partner doesn't hike…"
            ),
            height=80,
        )

        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button(
            "✈️  Generate My Itinerary & Map",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        if not destination.strip():
            st.error("⚠️ Please enter a region / country (question 1).")
        elif not trip_start_city.strip():
            st.error("⚠️ Please enter the city where the trip starts (question 3).")
        else:
            prefs = dict(
                destination=destination.strip(),
                trip_start_city=trip_start_city.strip(),
                trip_end_city=trip_end_city.strip(),
                month=month, year=year, duration=duration,
                group_size=group_size, group_type=group_type,
                trip_type=trip_type, activity_level=activity_level,
                pace=pace, budget=budget, accommodation=accommodation,
                transport=transport, max_drive=max_drive,
                nature_prefs=nature_prefs, activities=activities,
                hidden_vs_popular=hidden_vs_popular,
                food_prefs=food_prefs, dining_style=dining_style,
                special=special,
            )
            messages = [
                {"role": "system", "content": NATURE_PLANNER_SYSTEM_PROMPT},
                {"role": "user",   "content": prefs_to_prompt(prefs)},
            ]
            with st.spinner("🧭  Creating your personalised itinerary…"):
                itinerary = groq_chat(messages, max_tokens=4096)
            st.session_state.plan_itinerary = itinerary
            st.session_state.plan_stage = "itinerary"
            st.rerun()

# ── STAGE: itinerary — mountain animation while map builds ────────────────
elif st.session_state.plan_stage == "itinerary":

    col_title, col_btn = st.columns([5, 1])
    with col_title:
        st.markdown(
            "<h3 style='color:#F0F9FF;margin:0'>🏔️  Plotting your adventure…</h3>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🔄 Start over", key="so_itin"):
            reset_planner(); st.rerun()

    st.markdown("""
<style>
@keyframes hike {
    0%   { transform: translateX(-70px); }
    100% { transform: translateX(1400px); }
}
@keyframes twinkle {
    0%, 100% { opacity: .12; transform: scale(.7); }
    50%       { opacity: 1;   transform: scale(1.3); }
}
@keyframes cloud-drift {
    0%   { transform: translateX(-160px); }
    100% { transform: translateX(1600px); }
}
@keyframes dot-bounce {
    0%, 80%, 100% { transform: translateY(0);     opacity: .35; }
    40%            { transform: translateY(-9px);  opacity: 1;   }
}
</style>
<div style="position:relative;background:linear-gradient(180deg,#020810 0%,#07132E 45%,#0C1E40 100%);
    border-radius:16px;overflow:hidden;height:290px;border:1px solid #1F3D5C;margin-bottom:1.2rem;">

  <!-- stars -->
  <div style="position:absolute;width:3px;height:3px;background:#fff;border-radius:50%;top:7%;left:11%;animation:twinkle 2.3s ease-in-out infinite 0s"></div>
  <div style="position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;top:14%;left:26%;animation:twinkle 1.9s ease-in-out infinite .5s"></div>
  <div style="position:absolute;width:3px;height:3px;background:#fff;border-radius:50%;top:5%;left:43%;animation:twinkle 2.7s ease-in-out infinite 1.0s"></div>
  <div style="position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;top:19%;left:57%;animation:twinkle 2.1s ease-in-out infinite 1.3s"></div>
  <div style="position:absolute;width:3px;height:3px;background:#fff;border-radius:50%;top:8%;left:71%;animation:twinkle 2.5s ease-in-out infinite .2s"></div>
  <div style="position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;top:4%;left:85%;animation:twinkle 1.8s ease-in-out infinite .8s"></div>
  <div style="position:absolute;width:3px;height:3px;background:#fff;border-radius:50%;top:16%;left:94%;animation:twinkle 2.2s ease-in-out infinite 1.6s"></div>
  <div style="position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;top:11%;left:37%;animation:twinkle 2.0s ease-in-out infinite 0.3s"></div>

  <!-- clouds -->
  <div style="position:absolute;top:24px;width:100px;height:22px;background:rgba(255,255,255,.05);border-radius:20px;animation:cloud-drift 22s linear infinite 0s"></div>
  <div style="position:absolute;top:44px;width:70px;height:16px;background:rgba(255,255,255,.035);border-radius:20px;animation:cloud-drift 30s linear infinite 6s"></div>

  <!-- back mountains -->
  <div style="position:absolute;bottom:68px;left:-30px;width:0;height:0;
    border-left:170px solid transparent;border-right:170px solid transparent;
    border-bottom:210px solid #0C2348;"></div>
  <div style="position:absolute;bottom:68px;left:200px;width:0;height:0;
    border-left:210px solid transparent;border-right:210px solid transparent;
    border-bottom:250px solid #0A1F40;"></div>
  <div style="position:absolute;bottom:68px;right:-50px;width:0;height:0;
    border-left:190px solid transparent;border-right:190px solid transparent;
    border-bottom:220px solid #0C2348;"></div>
  <div style="position:absolute;bottom:68px;right:230px;width:0;height:0;
    border-left:150px solid transparent;border-right:150px solid transparent;
    border-bottom:180px solid #091D3C;"></div>

  <!-- front mountains -->
  <div style="position:absolute;bottom:60px;left:50px;width:0;height:0;
    border-left:140px solid transparent;border-right:140px solid transparent;
    border-bottom:170px solid #060F1F;"></div>
  <div style="position:absolute;bottom:60px;right:70px;width:0;height:0;
    border-left:160px solid transparent;border-right:160px solid transparent;
    border-bottom:190px solid #050D1D;"></div>

  <!-- ground -->
  <div style="position:absolute;bottom:0;left:0;right:0;height:62px;background:#030A18;border-top:1px solid #0D2040;"></div>

  <!-- trail -->
  <div style="position:absolute;bottom:60px;left:0;right:0;height:1px;
    background:linear-gradient(90deg,transparent 0%,rgba(56,189,248,.15) 20%,rgba(56,189,248,.15) 80%,transparent 100%);"></div>

  <!-- hiker -->
  <div style="position:absolute;bottom:57px;left:0;animation:hike 10s linear infinite;">
    <svg width="26" height="42" viewBox="0 0 26 42" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="13" cy="5" r="3.8" fill="#94BDDB"/>
      <line x1="13" y1="9" x2="13" y2="23" stroke="#94BDDB" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="13" y1="13" x2="4" y2="20" stroke="#94BDDB" stroke-width="2" stroke-linecap="round"/>
      <line x1="4" y1="20" x2="3" y2="30" stroke="#7FA8C0" stroke-width="1.6" stroke-linecap="round"/>
      <line x1="13" y1="13" x2="21" y2="18" stroke="#94BDDB" stroke-width="2" stroke-linecap="round"/>
      <line x1="13" y1="23" x2="7"  y2="34" stroke="#94BDDB" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="7"  y1="34" x2="4"  y2="41" stroke="#94BDDB" stroke-width="2" stroke-linecap="round"/>
      <line x1="13" y1="23" x2="19" y2="33" stroke="#94BDDB" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="19" y1="33" x2="23" y2="41" stroke="#94BDDB" stroke-width="2" stroke-linecap="round"/>
    </svg>
  </div>

  <!-- label -->
  <div style="position:absolute;bottom:10px;left:0;right:0;text-align:center;">
    <div style="color:#64748B;font-size:.82em;font-weight:500;letter-spacing:.5px;margin-bottom:9px;">
      Building your interactive map
    </div>
    <div style="display:inline-flex;gap:8px;align-items:center;">
      <div style="width:7px;height:7px;background:#38BDF8;border-radius:50%;animation:dot-bounce 1.4s ease-in-out infinite 0s"></div>
      <div style="width:7px;height:7px;background:#38BDF8;border-radius:50%;animation:dot-bounce 1.4s ease-in-out infinite .22s"></div>
      <div style="width:7px;height:7px;background:#38BDF8;border-radius:50%;animation:dot-bounce 1.4s ease-in-out infinite .44s"></div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    try:
        map_html, trip_data = build_map_html(st.session_state.plan_itinerary)
        st.session_state.plan_map_html = map_html
        st.session_state.plan_trip_data = trip_data
        st.session_state.plan_stage = "done"
    except (Exception, SystemExit) as e:
        st.error(f"Map build failed: {e}")

    if st.session_state.plan_stage == "done":
        st.rerun()

# ── STAGE: done — itinerary + map ─────────────────────────────────────────
elif st.session_state.plan_stage == "done":

    # ── Trip stat banner
    _td = st.session_state.get("plan_trip_data", {})
    _days = len(_td.get("days", []))
    _locs = sum(len(d.get("locations", [])) for d in _td.get("days", []))
    _stats = [
        ("📅", f"{_days}", "days planned"),
        ("📍", f"{_locs}", "locations mapped"),
        ("🗺️", "Interactive", "map ready"),
        ("⬇️", "Offline", "HTML included"),
    ]
    _stat_html = "".join(f"""
        <div style="background:rgba(14,165,233,0.07);border:1px solid rgba(14,165,233,0.18);
            border-radius:12px;padding:14px 20px;text-align:center;min-width:110px;">
            <div style="font-size:1.5em;margin-bottom:4px;">{ic}</div>
            <div style="color:#38BDF8;font-size:1.25em;font-weight:700;line-height:1.1;">{val}</div>
            <div style="color:#64748B;font-size:0.78em;font-weight:500;margin-top:2px;">{lbl}</div>
        </div>""" for ic, val, lbl in _stats)
    st.markdown(f"""
    <div style="
        background:linear-gradient(135deg,#041811,#062818);
        border:1px solid #0B3D20;border-radius:14px;
        padding:16px 22px;margin-bottom:1.2rem;
        animation:fadeUp 0.4s ease;">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
            <div style="width:10px;height:10px;background:#10B981;
                border-radius:50%;box-shadow:0 0 8px #10B981;"></div>
            <span style="color:#34D399;font-weight:700;font-size:1.05em;">
                Your trip map is ready!
            </span>
            <span style="color:#6EE7B7;font-size:0.88em;margin-left:4px;">
                · Download the HTML file to use offline in any browser
            </span>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">{_stat_html}</div>
    </div>
    """, unsafe_allow_html=True)

    col_title, col_btn = st.columns([5, 1])
    with col_title:
        st.markdown(
            "<h3 style='color:#F0F9FF;margin:0'>📋  Your Itinerary</h3>",
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🔄 Plan new", key="so_done"):
            reset_planner(); st.rerun()

    render_structured_itinerary(st.session_state.plan_trip_data)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        "<h3 style='color:#F0F9FF;margin:0 0 .8rem 0'>🗺️  Interactive Map</h3>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "⬇️  Download Map  (HTML · open in any browser · works offline)",
        data=st.session_state.plan_map_html,
        file_name="vacation_trip_map.html",
        mime="text/html",
        type="primary",
    )

    st.markdown("<br>", unsafe_allow_html=True)
    components.html(st.session_state.plan_map_html, height=700, scrolling=False)
