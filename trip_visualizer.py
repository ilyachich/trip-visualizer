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

# All icons use Font Awesome 4 (prefix='fa') — bundled with Folium, no CDN needed
TYPE_CONFIG: dict[str, dict] = {
    "hotel":      {"icon": "bed",         "color": "darkblue", "prefix": "fa"},
    "restaurant": {"icon": "cutlery",     "color": "red",      "prefix": "fa"},
    "activity":   {"icon": "camera",      "color": "green",    "prefix": "fa"},
    "poi":        {"icon": "map-marker",  "color": "orange",   "prefix": "fa"},
    "transport":  {"icon": "train",       "color": "gray",     "prefix": "fa"},
    "default":    {"icon": "info-circle", "color": "cadetblue","prefix": "fa"},
}

# Per-mode icon override for transport locations
TRANSPORT_MODE_CONFIG: dict[str, dict] = {
    "plane":    {"icon": "plane",   "color": "darkgray"},
    "train":    {"icon": "train",   "color": "gray"},
    "bus":      {"icon": "bus",     "color": "gray"},
    "metro":    {"icon": "subway",  "color": "darkpurple"},
    "ship":     {"icon": "ship",    "color": "darkblue"},
    "taxi":     {"icon": "taxi",    "color": "orange"},
    "car":      {"icon": "car",     "color": "gray"},
    "bicycle":  {"icon": "bicycle", "color": "green"},
}

TRANSPORT_MODE_EMOJI: dict[str, str] = {
    "plane":   "✈️",
    "train":   "🚂",
    "bus":     "🚌",
    "metro":   "🚇",
    "ship":    "🚢",
    "taxi":    "🚕",
    "car":     "🚗",
    "bicycle": "🚲",
}

TYPE_EMOJI = {
    "hotel":      "🏨",
    "restaurant": "🍽️",
    "activity":   "🎯",
    "poi":        "📍",
    "transport":  "🚆",
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
  "region": "city or region name, e.g. 'Tokyo & Kyoto' or 'Tuscany'",
  "days": [
    {
      "day_number": 1,
      "date": "string or null",
      "label": "Day 1 – City Name",
      "locations": [
        {
          "name": "Location Name",
          "type": "hotel|restaurant|activity|poi|transport",
          "transport_mode": "plane|train|bus|metro|ship|taxi|car|bicycle — only set when type=transport, else null",
          "description": "one-sentence description",
          "highlights": "2-3 key facts or highlights, comma-separated (null if none)",
          "tips": "one practical tip: opening hours, booking advice, best time to visit (null if none)",
          "cuisine": "cuisine type if restaurant, else null",
          "price_range": "$ | $$ | $$$ | $$$$ for restaurants/paid activities, else null",
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
      "description": "one-sentence description",
      "stars": 4,
      "amenities": "up to 3 amenities comma-separated, e.g. WiFi, Pool, Restaurant (null if unknown)"
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
- transport_mode: set for every transport entry — plane=airport/flight,
  train=railway/shinkansen, bus=bus station, metro=subway/underground,
  ship=ferry/cruise, taxi=taxi, car=rental car, bicycle=bike.
- If a hotel appears in the daily itinerary keep it there too (so the day
  route is complete), but also list it in accommodations.
- Use your knowledge to fill in highlights, tips, cuisine, stars etc. even if
  not explicitly stated in the text — these enrich the map popups.
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
        max_tokens=8192,
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

# ISO 3166-1 alpha-2 codes for common travel destinations
COUNTRY_CODES: dict[str, str] = {
    "japan": "jp", "france": "fr", "italy": "it", "spain": "es",
    "germany": "de", "united kingdom": "gb", "uk": "gb", "england": "gb",
    "united states": "us", "usa": "us", "australia": "au", "canada": "ca",
    "netherlands": "nl", "portugal": "pt", "greece": "gr", "turkey": "tr",
    "thailand": "th", "vietnam": "vn", "indonesia": "id", "singapore": "sg",
    "china": "cn", "south korea": "kr", "korea": "kr", "india": "in",
    "mexico": "mx", "brazil": "br", "argentina": "ar", "israel": "il",
    "egypt": "eg", "morocco": "ma", "south africa": "za", "kenya": "ke",
    "new zealand": "nz", "austria": "at", "switzerland": "ch", "belgium": "be",
    "sweden": "se", "norway": "no", "denmark": "dk", "finland": "fi",
    "poland": "pl", "czech republic": "cz", "hungary": "hu", "croatia": "hr",
}


def geocode(
    address: str,
    cache: dict[str, tuple | None],
    countrycode: str | None = None,
) -> tuple[float, float] | None:
    """Resolve an address to (lat, lon), with caching and rate-limiting."""
    cache_key = f"{address}|{countrycode}"
    if cache_key in cache:
        return cache[cache_key]

    headers = {"User-Agent": "TripVisualizer/1.0 (personal travel mapping tool)"}
    params: dict = {"q": address, "format": "json", "limit": 1}
    if countrycode:
        params["countrycodes"] = countrycode

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params=params, headers=headers, timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
            cache[cache_key] = coords
            time.sleep(1.1)   # Nominatim asks for ≤ 1 req/s
            return coords
    except Exception as exc:
        print(f"  ⚠  Could not geocode '{address}': {exc}", file=sys.stderr)

    cache[cache_key] = None
    return None


def geocode_trip(data: dict) -> dict[str, tuple | None]:
    """Geocode every address in the trip data; return filled cache."""
    cache: dict[str, tuple | None] = {}
    countrycode = COUNTRY_CODES.get(data.get("country", "").lower())
    print("Geocoding locations (Nominatim)…", file=sys.stderr)

    for day in data.get("days", []):
        for loc in day.get("locations", []):
            addr = loc.get("address") or loc["name"]
            print(f"  {addr}", file=sys.stderr)
            loc["_coords"] = geocode(addr, cache, countrycode)

    for acc in data.get("accommodations", []):
        addr = acc.get("address") or acc["name"]
        print(f"  {addr}  (accommodation)", file=sys.stderr)
        acc["_coords"] = geocode(addr, cache, countrycode)

    return cache


# ---------------------------------------------------------------------------
# Routing (OSRM — free, no key needed)
# ---------------------------------------------------------------------------

def get_route(start: tuple[float, float], end: tuple[float, float]) -> dict | None:
    """Get driving distance and duration between two coords via OSRM (free)."""
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{start[1]},{start[0]};{end[1]},{end[0]}"
    )
    try:
        resp = requests.get(url, params={"overview": "false"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "Ok":
            route = data["routes"][0]
            km    = route["distance"] / 1000
            mins  = route["duration"] / 60
            return {"km": round(km, 1), "drive_mins": round(mins)}
    except Exception:
        pass
    return None


def calculate_routes(data: dict) -> None:
    """
    For each day, compute driving distance/time between consecutive stops
    and store as _route_to_next on each location dict.
    """
    print("Calculating routes (OSRM)…", file=sys.stderr)
    for day in data.get("days", []):
        locs = sorted(
            [l for l in day.get("locations", []) if l.get("_coords")],
            key=lambda x: x.get("order", 99),
        )
        for i, loc in enumerate(locs):
            if i < len(locs) - 1:
                next_loc = locs[i + 1]
                route = get_route(loc["_coords"], next_loc["_coords"])
                if route:
                    route["next_name"] = next_loc["name"]
                    route["from_name"] = loc["name"]
                    print(
                        f"  {loc['name']} → {next_loc['name']}: "
                        f"{route['km']} km, {route['drive_mins']} min drive",
                        file=sys.stderr,
                    )
                loc["_route_to_next"] = route
                time.sleep(0.5)
            else:
                loc["_route_to_next"] = None


# ---------------------------------------------------------------------------
# Wikipedia images (free, no key needed)
# ---------------------------------------------------------------------------

def fetch_wiki_image(name: str) -> str | None:
    """Return a Wikipedia thumbnail URL for the given place name, or None.

    Uses Wikipedia's search API so fuzzy/partial names still find the right
    article (e.g. "Senso-ji Temple" → "Senso-ji", "Ichiran Ramen" → no result).
    """
    headers = {"User-Agent": "TripVisualizer/1.0"}
    try:
        # Step 1: search for the best-matching article title
        search_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": name,
                "format": "json",
                "srlimit": 1,
                "srnamespace": 0,
            },
            headers=headers,
            timeout=8,
        )
        results = search_resp.json().get("query", {}).get("search", [])
        if not results:
            return None
        title = results[0]["title"]

        # Step 2: fetch the thumbnail for that article
        img_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": title,
                "prop": "pageimages",
                "format": "json",
                "pithumbsize": 300,
                "piprop": "thumbnail",
            },
            headers=headers,
            timeout=8,
        )
        pages = img_resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
    except Exception:
        pass
    return None


def fetch_wiki_images(data: dict) -> None:
    """Fetch Wikipedia thumbnail for every location and store as _image_url."""
    print("Fetching place images (Wikipedia)…", file=sys.stderr)
    seen: dict[str, str | None] = {}
    for day in data.get("days", []):
        for loc in day.get("locations", []):
            name = loc["name"]
            if name not in seen:
                url = fetch_wiki_image(name)
                seen[name] = url
                status = "ok" if url else "none"
                print(f"  {name}: {status}", file=sys.stderr)
                time.sleep(0.3)
            loc["_image_url"] = seen[name]
    for acc in data.get("accommodations", []):
        name = acc["name"]
        if name not in seen:
            url = fetch_wiki_image(name)
            seen[name] = url
            time.sleep(0.3)
        acc["_image_url"] = seen[name]


# ---------------------------------------------------------------------------
# Map building
# ---------------------------------------------------------------------------

def _route_badge(route: dict | None) -> str:
    """Return an HTML snippet showing from → to distance and travel time."""
    if not route:
        return ""
    km        = route["km"]
    mins      = route["drive_mins"]
    next_name = route.get("next_name", "next stop")
    walk      = round(km / 0.08)  # ~5 km/h walking ≈ 0.083 km/min
    if km < 1.5:
        travel = f"🚶 {walk} min walk"
    else:
        transit = round(mins * 1.35)
        travel  = f"🚗 {mins} min &nbsp;·&nbsp; 🚇 ~{transit} min"
    return (
        f'<div style="margin-top:6px;padding-top:6px;border-top:1px solid #eee;'
        f'font-size:11px;color:#555">'
        f'<b>To {next_name}:</b> {km} km &nbsp;|&nbsp; {travel}</div>'
    )


def _popup_html(
    title: str,
    subtitle: str,
    description: str,
    *,
    highlights: str | None = None,
    tips: str | None = None,
    cuisine: str | None = None,
    price_range: str | None = None,
    stars: int | None = None,
    amenities: str | None = None,
    image_url: str | None = None,
    route: dict | None = None,
) -> folium.Popup:
    img_html = ""
    if image_url:
        img_html = (
            f'<a href="{image_url}" target="_blank" title="Click to enlarge">'
            f'<img src="{image_url}" style="width:100%;border-radius:4px;'
            f'margin-bottom:8px;cursor:zoom-in" /></a>'
        )

    stars_html = ""
    if stars:
        stars_html = f'<span style="color:#f0a500">{"★" * int(stars)}{"☆" * (5 - int(stars))}</span> &nbsp;'

    extra_rows = ""
    if highlights:
        extra_rows += f'<div style="margin-top:5px;font-size:11px;color:#555">✨ {highlights}</div>'
    if tips:
        extra_rows += f'<div style="margin-top:4px;font-size:11px;color:#2980b9">💡 {tips}</div>'
    if cuisine:
        label = f"{cuisine}"
        if price_range:
            label += f" · {price_range}"
        extra_rows += f'<div style="margin-top:4px;font-size:11px;color:#888">🍴 {label}</div>'
    if amenities:
        extra_rows += f'<div style="margin-top:4px;font-size:11px;color:#888">🏷 {amenities}</div>'

    html = f"""
    <div style="font-family:Arial,sans-serif;min-width:220px;max-width:300px">
      {img_html}
      <p style="margin:0 0 2px 0;font-size:14px;font-weight:bold;color:#222">{title}</p>
      <p style="margin:0 0 5px 0;font-size:11px;color:#888">{stars_html}{subtitle}</p>
      <p style="margin:0;font-size:12px;color:#444">{description}</p>
      {extra_rows}
      {_route_badge(route)}
    </div>"""
    return folium.Popup(html, max_width=320)


def build_map(data: dict) -> folium.Map:
    """Create the Folium map from geocoded trip data."""

    # Collect all coordinates
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
        min_lat = min(c[0] for c in all_coords)
        max_lat = max(c[0] for c in all_coords)
        min_lon = min(c[1] for c in all_coords)
        max_lon = max(c[1] for c in all_coords)
        center  = [(min_lat + max_lat) / 2, (min_lon + max_lon) / 2]
    else:
        center  = [20.0, 0.0]
        min_lat = max_lat = min_lon = max_lon = None
        print("Warning: no coordinates resolved — map will show world view.",
              file=sys.stderr)

    m = folium.Map(location=center, zoom_start=7, tiles="CartoDB positron")

    # Auto-fit zoom to the actual travel area
    if min_lat is not None:
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=[40, 40])

    # ── Per-day layers ────────────────────────────────────────────────────
    for i, day in enumerate(data.get("days", [])):
        color      = DAY_COLORS[i % len(DAY_COLORS)]
        day_label  = day.get("label") or f"Day {day['day_number']}"
        fg         = folium.FeatureGroup(name=f"📅 {day_label}", show=True)
        day_coords: list[tuple[float, float]] = []
        route_segments: list[str] = []

        sorted_locs = sorted(day.get("locations", []), key=lambda x: x.get("order", 99))

        for loc in sorted_locs:
            coords = loc.get("_coords")
            if not coords:
                continue
            day_coords.append(coords)

            loc_type  = loc.get("type", "default")
            cfg       = TYPE_CONFIG.get(loc_type, TYPE_CONFIG["default"])
            emoji     = TYPE_EMOJI.get(loc_type, TYPE_EMOJI["default"])
            # For transport, override icon and emoji based on transport_mode
            if loc_type == "transport":
                mode = (loc.get("transport_mode") or "train").lower()
                mode_cfg = TRANSPORT_MODE_CONFIG.get(mode, TRANSPORT_MODE_CONFIG["train"])
                cfg   = {"icon": mode_cfg["icon"], "color": mode_cfg["color"], "prefix": "fa"}
                emoji = TRANSPORT_MODE_EMOJI.get(mode, "🚆")
            route_nxt = loc.get("_route_to_next")

            if route_nxt:
                route_segments.append(
                    f"{loc['name']} → next: {route_nxt['km']} km, "
                    f"{route_nxt['drive_mins']} min drive"
                )

            folium.Marker(
                location=coords,
                popup=_popup_html(
                    f"{emoji} {loc['name']}",
                    f"Day {day['day_number']} · {loc_type.title()}",
                    loc.get("description", ""),
                    highlights  = loc.get("highlights"),
                    tips        = loc.get("tips"),
                    cuisine     = loc.get("cuisine"),
                    price_range = loc.get("price_range"),
                    image_url   = loc.get("_image_url"),
                    route       = route_nxt,
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
            total_km   = sum(s.get("km", 0) for s in
                             [l.get("_route_to_next") or {} for l in sorted_locs if l.get("_coords")])
            total_mins = sum(s.get("drive_mins", 0) for s in
                             [l.get("_route_to_next") or {} for l in sorted_locs if l.get("_coords")])
            line_tip   = day_label
            if total_km:
                line_tip += f" — {round(total_km, 1)} km total, ~{total_mins} min drive"

            folium.PolyLine(
                locations=day_coords,
                color=color,
                weight=3,
                opacity=0.85,
                tooltip=line_tip,
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
            popup=_popup_html(
                f"🏨 {acc['name']}",
                f"Check-in: Day {ci}  ·  Check-out: Day {co}",
                acc.get("description", ""),
                stars     = acc.get("stars"),
                amenities = acc.get("amenities"),
                image_url = acc.get("_image_url"),
            ),
            tooltip=f"🏨 {acc['name']}  (Days {ci}–{co})",
            icon=folium.Icon(color="darkblue", icon="home", prefix="glyphicon"),
        ).add_to(acc_fg)
    acc_fg.add_to(m)

    # ── Legend ────────────────────────────────────────────────────────────
    days = data.get("days", [])
    region  = data.get("region", "")
    country = data.get("country", "")
    location_line = ", ".join(filter(None, [region, country]))

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

    location_html = (
        f'<div style="font-size:11px;color:#888;margin-bottom:8px">📍 {location_line}</div>'
        if location_line else ""
    )

    legend = f"""
    <div style="
        position:fixed;bottom:30px;left:30px;z-index:9999;
        background:white;padding:12px 16px;border-radius:8px;
        border:1px solid #ccc;box-shadow:2px 2px 8px rgba(0,0,0,.2);
        font-family:Arial,sans-serif;font-size:12px;min-width:170px">
      <b style="display:block;margin-bottom:4px;font-size:13px">
        {data.get('trip_name','Trip')}
      </b>
      {location_html}
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
        help="Groq API key (overrides GROQ_API_KEY env var). Free at console.groq.com",
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
    calculate_routes(trip_data)
    fetch_wiki_images(trip_data)
    trip_map = build_map(trip_data)

    out = Path(args.output)
    trip_map.save(str(out))

    print(f"\n✓ Map saved → {out.resolve()}", file=sys.stderr)
    print(f"  Open in browser: file:///{out.resolve().as_posix()}", file=sys.stderr)


if __name__ == "__main__":
    main()
