#!/usr/bin/env python3
"""
Trip Visualizer
===============
Parses a free-text trip description with Groq (FREE) and renders an
interactive HTML map (Folium / Leaflet) with:
  - Per-day colour-coded routes
  - Typed markers  (hotel, restaurant, activity, POI, transport)
  - A stay-points layer showing every accommodation
  - Toggleable layer control + legend

Usage
-----
    python trip_visualizer.py trip.txt
    python trip_visualizer.py trip.txt -o my_trip.html --json-output parsed.json

Requirements  (all free)
------------------------
    pip install folium groq requests

Get a free Groq API key at: https://console.groq.com
Set it once:  setx GROQ_API_KEY "your-key-here"   (Windows)
Or pass it:   python trip_visualizer.py trip.txt --api-key YOUR_KEY
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from groq import Groq
import folium
import requests

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

DAY_COLORS = [
    "#E74C3C",  # red
    "#2980B9",  # blue
    "#27AE60",  # green
    "#E67E22",  # orange
    "#8E44AD",  # purple
    "#16A085",  # teal
    "#C0392B",  # dark red
    "#2471A3",  # dark blue
    "#1E8449",  # dark green
    "#B7950B",  # gold
]

# Glyphicon names work without external CDN; FA-4 names also supported with prefix='fa'
TYPE_CONFIG: dict[str, dict] = {
    "hotel":      {"icon": "home",         "color": "darkblue",  "prefix": "glyphicon"},
    "restaurant": {"icon": "cutlery",      "color": "red",       "prefix": "glyphicon"},
    "activity":   {"icon": "camera",       "color": "green",     "prefix": "glyphicon"},
    "poi":        {"icon": "star",         "color": "orange",    "prefix": "glyphicon"},
    "transport":  {"icon": "plane",        "color": "gray",      "prefix": "glyphicon"},
    "default":    {"icon": "info-sign",    "color": "cadetblue", "prefix": "glyphicon"},
}

TYPE_EMOJI = {
    "hotel":      "🏨",
    "restaurant": "🍽️",
    "activity":   "🎯",
    "poi":        "📍",
    "transport":  "✈️",
    "default":    "📌",
}

# ---------------------------------------------------------------------------
# Claude parsing
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a travel itinerary parser. Extract structured data from trip descriptions.
Return ONLY valid JSON — no markdown fences, no explanation.

Schema:
{
  "trip_name": "string",
  "country": "string",
  "days": [
    {
      "day_number": 1,
      "date": "string or null",
      "label": "Day 1 – City Name",
      "locations": [
        {
          "name": "Location Name",
          "type": "hotel|restaurant|activity|poi|transport",
          "description": "one-sentence description",
          "address": "full address including city and country",
          "order": 1
        }
      ]
    }
  ],
  "accommodations": [
    {
      "name": "Hotel Name",
      "address": "full address including city and country",
      "check_in_day": 1,
      "check_out_day": 3,
      "description": "one-sentence description"
    }
  ]
}

Rules:
- `address` must always contain city + country so geocoding works reliably.
- `accommodations` lists each hotel/stay once (not repeated per day).
  Set check_in_day / check_out_day from context.
- `order` is the chronological visit order within a day (1, 2, 3 …).
- Types: hotel=accommodation, restaurant=dining, activity=tours/experiences,
         poi=sight/landmark, transport=airport/station/transit hub.
- If a hotel appears in the daily itinerary keep it there too (so the day
  route is complete), but also list it in accommodations.
"""


def parse_trip(text: str, api_key: str | None = None) -> dict:
    """Call Groq (free tier) to turn free-form trip text into structured JSON."""
    import os
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        print(
            "Error: Groq API key not found.\n"
            "  Get a free key at https://console.groq.com\n"
            "  Then run:  setx GROQ_API_KEY \"your-key-here\"  (open a new terminal after)",
            file=sys.stderr,
        )
        sys.exit(1)

    client = Groq(api_key=key)

    print("Parsing trip description with Groq (free)…", file=sys.stderr)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Parse this trip:\n\n{text}"},
        ],
        max_tokens=4096,
    )
    raw = response.choices[0].message.content.strip()

    # Strip accidental markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw.strip())

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: Groq returned invalid JSON — {exc}", file=sys.stderr)
        print("Raw response:", raw[:500], file=sys.stderr)
        sys.exit(1)

    n_days = len(data.get("days", []))
    n_locs = sum(len(d.get("locations", [])) for d in data.get("days", []))
    n_acc  = len(data.get("accommodations", []))
    print(f"  → {n_days} days · {n_locs} locations · {n_acc} accommodations",
          file=sys.stderr)
    return data


# ---------------------------------------------------------------------------
# Geocoding (OpenStreetMap Nominatim — free, no key needed)
# ---------------------------------------------------------------------------

def geocode(address: str, cache: dict[str, tuple | None]) -> tuple[float, float] | None:
    """Resolve an address to (lat, lon), with caching and rate-limiting."""
    if address in cache:
        return cache[address]

    headers = {"User-Agent": "TripVisualizer/1.0 (personal travel mapping tool)"}
    params  = {"q": address, "format": "json", "limit": 1}

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params, headers=headers, timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
            cache[address] = coords
            time.sleep(1.1)   # Nominatim asks for ≤ 1 req/s
            return coords
    except Exception as exc:
        print(f"  ⚠  Could not geocode '{address}': {exc}", file=sys.stderr)

    cache[address] = None
    return None


def geocode_trip(data: dict) -> dict[str, tuple | None]:
    """Geocode every address in the trip data; return filled cache."""
    cache: dict[str, tuple | None] = {}
    print("Geocoding locations (Nominatim)…", file=sys.stderr)

    for day in data.get("days", []):
        for loc in day.get("locations", []):
            addr = loc.get("address") or loc["name"]
            print(f"  {addr}", file=sys.stderr)
            loc["_coords"] = geocode(addr, cache)

    for acc in data.get("accommodations", []):
        addr = acc.get("address") or acc["name"]
        print(f"  {addr}  (accommodation)", file=sys.stderr)
        acc["_coords"] = geocode(addr, cache)

    return cache


# ---------------------------------------------------------------------------
# Map building
# ---------------------------------------------------------------------------

def _popup(title: str, subtitle: str, description: str) -> folium.Popup:
    html = f"""
    <div style="font-family:Arial,sans-serif;min-width:200px;max-width:280px">
      <p style="margin:0 0 6px 0;font-size:14px;font-weight:bold;color:#222">{title}</p>
      <p style="margin:0 0 6px 0;font-size:11px;color:#888">{subtitle}</p>
      <p style="margin:0;font-size:12px;color:#444">{description}</p>
    </div>"""
    return folium.Popup(html, max_width=300)


def build_map(data: dict) -> folium.Map:
    """Create the Folium map from geocoded trip data."""

    # Collect all coordinates for centering
    all_coords = [
        loc["_coords"]
        for day in data.get("days", [])
        for loc in day.get("locations", [])
        if loc.get("_coords")
    ] + [
        acc["_coords"]
        for acc in data.get("accommodations", [])
        if acc.get("_coords")
    ]

    if all_coords:
        center = [
            sum(c[0] for c in all_coords) / len(all_coords),
            sum(c[1] for c in all_coords) / len(all_coords),
        ]
        zoom = 12
    else:
        center = [20.0, 0.0]
        zoom = 2
        print("Warning: no coordinates resolved — map will show world view.",
              file=sys.stderr)

    m = folium.Map(location=center, zoom_start=zoom, tiles="CartoDB positron")

    # ── Per-day layers ────────────────────────────────────────────────────
    for i, day in enumerate(data.get("days", [])):
        color      = DAY_COLORS[i % len(DAY_COLORS)]
        day_label  = day.get("label") or f"Day {day['day_number']}"
        fg         = folium.FeatureGroup(name=f"📅 {day_label}", show=True)
        day_coords: list[tuple[float, float]] = []

        for loc in sorted(day.get("locations", []), key=lambda x: x.get("order", 99)):
            coords = loc.get("_coords")
            if not coords:
                continue
            day_coords.append(coords)

            loc_type = loc.get("type", "default")
            cfg      = TYPE_CONFIG.get(loc_type, TYPE_CONFIG["default"])
            emoji    = TYPE_EMOJI.get(loc_type, TYPE_EMOJI["default"])

            folium.Marker(
                location=coords,
                popup=_popup(
                    f"{emoji} {loc['name']}",
                    f"Day {day['day_number']} · {loc_type.title()}",
                    loc.get("description", ""),
                ),
                tooltip=f"Day {day['day_number']}: {loc['name']}",
                icon=folium.Icon(
                    color=cfg["color"],
                    icon=cfg["icon"],
                    prefix=cfg["prefix"],
                ),
            ).add_to(fg)

        # Dashed route line for the day
        if len(day_coords) >= 2:
            folium.PolyLine(
                locations=day_coords,
                color=color,
                weight=3,
                opacity=0.85,
                tooltip=day_label,
                dash_array="10 6",
            ).add_to(fg)

        fg.add_to(m)

    # ── Accommodations layer ──────────────────────────────────────────────
    acc_fg = folium.FeatureGroup(name="🏨 Accommodations", show=True)
    for acc in data.get("accommodations", []):
        coords = acc.get("_coords")
        if not coords:
            continue
        ci = acc.get("check_in_day",  "?")
        co = acc.get("check_out_day", "?")

        folium.Marker(
            location=coords,
            popup=_popup(
                f"🏨 {acc['name']}",
                f"Check-in: Day {ci}  ·  Check-out: Day {co}",
                acc.get("description", ""),
            ),
            tooltip=f"🏨 {acc['name']}  (Days {ci}–{co})",
            icon=folium.Icon(color="darkblue", icon="home", prefix="glyphicon"),
        ).add_to(acc_fg)
    acc_fg.add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────
    days = data.get("days", [])
    def _day_row(i: int, day: dict) -> str:
        color = DAY_COLORS[i % len(DAY_COLORS)]
        label = day.get("label") or f"Day {day['day_number']}"
        return (
            f'<div style="margin:2px 0">'
            f'<span style="display:inline-block;width:22px;height:3px;'
            f'background:{color};vertical-align:middle;margin-right:6px"></span>'
            f'{label}</div>'
        )

    day_rows = "".join(_day_row(i, day) for i, day in enumerate(days))

    legend = f"""
    <div style="
        position:fixed;bottom:30px;left:30px;z-index:9999;
        background:white;padding:12px 16px;border-radius:8px;
        border:1px solid #ccc;box-shadow:2px 2px 8px rgba(0,0,0,.2);
        font-family:Arial,sans-serif;font-size:12px;min-width:170px">
      <b style="display:block;margin-bottom:8px;font-size:13px">
        {data.get('trip_name','Trip')}
      </b>
      <div>🏨 Hotel / Stay</div>
      <div>🍽️ Restaurant</div>
      <div>🎯 Activity</div>
      <div>📍 Point of Interest</div>
      <div>✈️ Transport</div>
      <div style="margin-top:8px;border-top:1px solid #eee;padding-top:8px">
        <b>Days</b>
        {day_rows}
      </div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend))

    # ── Layer control ─────────────────────────────────────────────────────
    folium.LayerControl(collapsed=False).add_to(m)

    return m


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualise a trip description as an interactive map."
    )
    parser.add_argument(
        "input",
        help="Path to trip text file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output", "-o",
        default="trip_map.html",
        help="Output HTML file (default: trip_map.html).",
    )
    parser.add_argument(
        "--api-key",
        help="Google API key (overrides GOOGLE_API_KEY env var). Free at aistudio.google.com",
    )
    parser.add_argument(
        "--json-output",
        metavar="FILE",
        help="Save the parsed trip JSON to this file (for inspection / reuse).",
    )
    args = parser.parse_args()

    # Read trip text
    if args.input == "-":
        print("Reading from stdin…", file=sys.stderr)
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.exists():
            print(f"Error: file not found — {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text(encoding="utf-8")

    if not text.strip():
        print("Error: input is empty.", file=sys.stderr)
        sys.exit(1)

    # Parse → geocode → render
    trip_data = parse_trip(text, api_key=args.api_key)

    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(trip_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Parsed JSON → {args.json_output}", file=sys.stderr)

    geocode_trip(trip_data)
    trip_map = build_map(trip_data)

    out = Path(args.output)
    trip_map.save(str(out))

    print(f"\n✓ Map saved → {out.resolve()}", file=sys.stderr)
    print(f"  Open in browser: file:///{out.resolve().as_posix()}", file=sys.stderr)


if __name__ == "__main__":
    main()
