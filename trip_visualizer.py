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
import html as html_lib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

from groq import Groq
import folium
from folium.plugins import PolyLineTextPath
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
    "poi":        "🏛️",
    "transport":  "🚆",
    "default":    "📌",
}

# ---------------------------------------------------------------------------
# Vacation Trip Planner (interactive trip planning)
# ---------------------------------------------------------------------------

NATURE_PLANNER_SYSTEM_PROMPT = """\
You are Vacation Trip Planner, an expert travel planner specializing in \
nature-focused, efficient, and realistic itineraries.

CORE PRINCIPLES:
- Minimize driving: default max 1–1.5 hours per day
- Limit accommodation changes: 2 base locations for 5–8 day trips
- Focus on nature: lakes, mountains, waterfalls, forests, scenic drives
- Prefer hidden gems over overcrowded tourist spots
- Mix active and relaxed days
- Recommend local restaurants and authentic experiences

BEHAVIOR:
- If key details are missing, ask 3–5 concise clarifying questions BEFORE generating
- After collecting answers, briefly confirm your plan assumptions (2–3 bullet points)
- When user confirms, generate the full itinerary
- Never suggest unrealistic driving times or rushed plans

QUESTIONS TO CONSIDER ASKING (pick the most relevant 3–5):
- Destination / country or region
- Trip duration (number of days)
- Travel season or dates
- Group composition (solo, couple, family with children, etc.)
- Activity level (relaxed, moderate, active/hiking)
- Must-have activities (rafting, cycling, swimming, etc.)
- Accommodation preference (budget, mid-range, luxury)
- Starting/ending city

ITINERARY FORMAT — use exactly this structure when generating the final itinerary:

[Trip Name] – [N] Days ([Region, Country])

Accommodations:
- [Hotel Name], [City], [Country]: Days [check-in]–[check-out]

Day 1 – [City or Theme]
[Morning/afternoon/evening activities. Use real, geocodable place names.]
Check in to [Hotel Name] in [City].
[Dinner/lunch at specific named restaurant], [City].

Day 2 – [Theme]
[Activities with real place names, brief descriptions, transport modes if relevant.]

(Repeat for all days. Always use specific, real place names that can be found on a map.)
"""

# Used by the Streamlit web app — single LLM call that generates JSON directly
# so the displayed itinerary and the map always come from the same data source.
TRIP_PLANNER_JSON_PROMPT = """\
You are an expert travel planner. Given trip preferences, generate a complete, realistic \
trip itinerary and return it as VALID JSON ONLY — no markdown fences, no explanation, \
nothing before or after the JSON object.

Schema:
{
  "trip_name": "descriptive name, e.g. 'Slovenian Alps & Lakes – 7 Days'",
  "country": "country name",
  "region": "city or region name, e.g. 'Ljubljana & Lake Bled' or 'Dolomites'",
  "days": [
    {
      "day_number": 1,
      "date": null,
      "label": "Day 1 – City or Theme",
      "locations": [
        {
          "name": "Location Name",
          "type": "hotel|restaurant|activity|poi|transport",
          "transport_mode": "plane|train|bus|metro|ship|taxi|car|bicycle — only for transport type, else null",
          "description": "one-sentence description",
          "highlights": "2-3 key facts, comma-separated (null if none)",
          "tips": "one practical tip: opening hours, booking advice (null if none)",
          "cuisine": "cuisine type if restaurant, else null",
          "price_range": "$ | $$ | $$$ | $$$$ for restaurants/paid activities, else null",
          "address": "full address including city and country",
          "order": 1,
          "trail_distance_km": null,
          "elevation_gain_m": null,
          "difficulty": null,
          "duration_hours": null
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
      "amenities": "WiFi, Pool, Restaurant (null if unknown)"
    }
  ]
}

Rules:
- Use real, searchable, geocodable place names (e.g. "Bled Castle, Bled, Slovenia" not "the castle")
- Every address MUST include city and country — required for map pin placement
- Include AT LEAST 5 locations per day: hotel + 2 or more sights/activities + 1 restaurant minimum; active/hiking days should have 5-7 entries
- Day 1 MUST include: arrival transport or hotel check-in, at least 2 named local attractions near the arrival city, and at least 1 restaurant — all with geocodable addresses in that city
- Hiking and trekking activities MUST fill trail_distance_km (numeric km), elevation_gain_m (numeric m), difficulty (easy/moderate/hard/expert), duration_hours (numeric hours) — these are shown in the map popup and trail links are generated from them
- For non-hiking locations, leave trail_distance_km/elevation_gain_m/difficulty/duration_hours as null
- Minimize accommodation changes: 2–3 hotels max for a week-long trip
- Set check_in_day / check_out_day correctly for each hotel
- order = chronological visit sequence within a day, starting at 1
- Types: hotel=accommodation, restaurant=dining, activity=tours/experiences/hiking, poi=sight/landmark, transport=airport/station
- transport_mode only for transport entries: plane|train|bus|metro|ship|taxi|car|bicycle
- Include hotels in each day's locations list (for a complete route), AND in accommodations separately
- Keep driving time per day within the specified maximum
- Fill highlights, tips, cuisine, stars, amenities from your knowledge — these enrich the map popups
- Generate exactly the requested number of days
- Prefer specific named trails, peaks, viewpoints, and local restaurants over generic descriptions
- For hiking: name the specific trail (e.g. "Triglav Summit Trail via Kredarica Hut") not just "hiking"
"""


def run_nature_planner(api_key: str | None = None) -> str:
    """Interactive Vacation Trip Planner — returns a trip itinerary as plain text."""
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
    messages: list[dict] = [{"role": "system", "content": NATURE_PLANNER_SYSTEM_PROMPT}]

    print("\n" + "=" * 60)
    print("  🌿  Vacation Trip Planner")
    print("=" * 60)
    print("Describe your ideal trip. Examples:")
    print("  7-day nature trip in Slovenia, couple, moderate hiking")
    print("  Hidden lakes and mountains in Austria, 5 days, relaxed")
    print()

    user_input = input("Your trip idea: ").strip()
    if not user_input:
        print("No input provided.", file=sys.stderr)
        sys.exit(1)

    messages.append({"role": "user", "content": user_input})

    # ── Turn 1: clarifying questions ──────────────────────────────────────
    print("\nThinking…")
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1024,
    )
    reply = resp.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": reply})
    print(f"\n{reply}\n")

    answers = input("Your answers: ").strip()
    if not answers:
        answers = "Please proceed with reasonable assumptions."
    messages.append({"role": "user", "content": answers})

    # ── Turn 2: plan summary / confirmation ───────────────────────────────
    print("\nPreparing your plan…")
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1024,
    )
    reply = resp.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": reply})
    print(f"\n{reply}\n")

    confirm = input("Proceed? (press Enter to confirm, or describe changes): ").strip()
    if confirm.lower() in ("", "yes", "y", "ok", "sure", "go", "proceed"):
        messages.append({"role": "user", "content": "Yes, generate the full detailed itinerary now."})
    else:
        messages.append({"role": "user", "content": f"{confirm}. Now generate the full detailed itinerary."})

    # ── Turn 3: full itinerary ────────────────────────────────────────────
    print("\nGenerating your itinerary…")
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=4096,
    )
    itinerary = resp.choices[0].message.content.strip()

    print("\n" + "=" * 60)
    print("  📋  Generated Itinerary")
    print("=" * 60)
    print(itinerary)
    print("=" * 60 + "\n")

    return itinerary


# ---------------------------------------------------------------------------
# Trip text parsing
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


def _nominatim(
    query: str,
    countrycode: str | None,
    headers: dict,
) -> tuple[float, float] | None:
    params: dict = {"q": query, "format": "json", "limit": 1}
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
            return (float(results[0]["lat"]), float(results[0]["lon"]))
    except Exception:
        pass
    finally:
        time.sleep(1.1)   # Nominatim asks for ≤ 1 req/s
    return None


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
    parts   = [p.strip() for p in address.split(",") if p.strip()]

    # Attempt 1: full address + country restriction
    result = _nominatim(address, countrycode, headers)

    # Attempt 2: full address, no country restriction
    if not result and countrycode:
        result = _nominatim(address, None, headers)

    # Attempt 3: "name, country" (first + last comma-parts)
    if not result and len(parts) >= 3:
        result = _nominatim(f"{parts[0]}, {parts[-1]}", None, headers)

    # Attempt 4: city/area level — second-to-last + last parts, e.g. "Mokra Gora, Serbia"
    if not result and len(parts) >= 2:
        result = _nominatim(f"{parts[-2]}, {parts[-1]}", countrycode, headers)

    # Attempt 5: strip common type/descriptor words, keep the core name + country
    if not result and parts:
        _NOISE = {"restaurant", "hotel", "hostel", "guesthouse", "museum",
                  "church", "temple", "palace", "castle", "park", "garden",
                  "airport", "station", "terminal", "market", "cafe", "bar",
                  "national", "nature", "reserve", "trail", "route", "path",
                  "waterfall", "falls", "lake", "mount", "mountain", "peak",
                  "viewpoint", "lookout", "center", "centre", "complex", "resort",
                  "ski", "hut", "refuge", "lodge", "inn", "spa", "beach", "bay"}
        name_words = parts[0].split()
        stripped   = " ".join(w for w in name_words if w.lower() not in _NOISE).strip()
        if stripped and stripped != parts[0]:
            # Try stripped name + country for context
            q = f"{stripped}, {parts[-1]}" if len(parts) >= 2 else stripped
            result = _nominatim(q, countrycode, headers)

    # Attempt 6: strip diacritics / accents (helps when LLM uses slightly wrong spelling)
    if not result:
        ascii_addr = "".join(
            c for c in unicodedata.normalize("NFD", address)
            if unicodedata.category(c) != "Mn"
        )
        if ascii_addr != address:
            result = _nominatim(ascii_addr, countrycode, headers)

    cache[cache_key] = result
    if not result:
        print(f"  ⚠  Could not geocode '{address}'", file=sys.stderr)
    return result


def _city_country_fallback(address: str, name: str, countrycode: str | None,
                            cache: dict, headers: dict) -> tuple[float, float] | None:
    """Last-resort: geocode just 'city, country' so the pin at least appears in the right area."""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    # Try "city, country" from the address parts
    if len(parts) >= 2:
        city_q = f"{parts[-2]}, {parts[-1]}"
        r = geocode(city_q, cache, countrycode)
        if r:
            return r
    # Try just the place name as-is
    if name and name not in address:
        r = geocode(name, cache, countrycode)
        if r:
            return r
    return None


def _region_fallback(data: dict, cache: dict, countrycode: str | None,
                     label: str) -> tuple[float, float] | None:
    """Absolute last resort: geocode the trip's region or country."""
    country_name = data.get("country", "")
    region       = data.get("region", "")
    for q in [
        f"{region}, {country_name}" if region and country_name else None,
        region if region else None,
        country_name if country_name else None,
    ]:
        if not q:
            continue
        r = geocode(q, cache, countrycode)
        if r:
            print(f"    ↳ trip-region pin for '{label}'", file=sys.stderr)
            return r
    return None


def geocode_trip(data: dict) -> dict[str, tuple | None]:
    """Geocode every address in the trip data; return filled cache."""
    cache: dict[str, tuple | None] = {}
    countrycode = COUNTRY_CODES.get(data.get("country", "").lower())
    headers = {"User-Agent": "TripVisualizer/1.0 (personal travel mapping tool)"}
    print("Geocoding locations (Nominatim)…", file=sys.stderr)

    for day in data.get("days", []):
        for loc in day.get("locations", []):
            addr = loc.get("address") or loc["name"]
            name = loc.get("name", "")
            print(f"  {addr}", file=sys.stderr)
            coords = geocode(addr, cache, countrycode)

            if coords is None and name and name != addr:
                # Try bare place name (no address context)
                coords = geocode(name, cache, countrycode)

            if coords is None and loc.get("address"):
                # City-level fallback
                coords = _city_country_fallback(
                    loc["address"], name, countrycode, cache, headers
                )
                if coords:
                    print(f"    ↳ city-level pin for '{name}'", file=sys.stderr)

            if coords is None:
                # Absolute last resort — place pin at trip region
                coords = _region_fallback(data, cache, countrycode, name)

            loc["_coords"] = coords

    for acc in data.get("accommodations", []):
        addr = acc.get("address") or acc["name"]
        name = acc.get("name", "")
        print(f"  {addr}  (accommodation)", file=sys.stderr)
        coords = geocode(addr, cache, countrycode)
        if coords is None and acc.get("address"):
            coords = _city_country_fallback(
                acc["address"], name, countrycode, cache, headers
            )
        if coords is None:
            coords = _region_fallback(data, cache, countrycode, name)
        acc["_coords"] = coords

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
    if km < 0.05:
        return ""
    mins      = route["drive_mins"]
    next_name = route.get("next_name", "next stop")
    if len(next_name) > 35:
        next_name = next_name[:33] + "…"
    walk      = round(km / 0.08)  # ~5 km/h walking ≈ 0.083 km/min
    if km < 1.5:
        travel = f"🚶 {max(walk, 1)} min walk"
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
    trail_distance_km: float | None = None,
    elevation_gain_m: int | None = None,
    difficulty: str | None = None,
    duration_hours: float | None = None,
    alltrails_url: str | None = None,
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

    # Hiking stats block
    if any(v is not None for v in (trail_distance_km, elevation_gain_m, difficulty, duration_hours)):
        diff_color = {"easy": "#27ae60", "moderate": "#f39c12",
                      "hard": "#e74c3c", "expert": "#8e44ad"}.get(
            (difficulty or "").lower(), "#555"
        )
        parts = []
        if trail_distance_km is not None:
            parts.append(f"📏 {trail_distance_km} km")
        if elevation_gain_m is not None:
            parts.append(f"⬆ {elevation_gain_m} m gain")
        if duration_hours is not None:
            h = int(duration_hours)
            m = round((duration_hours - h) * 60)
            parts.append(f"⏱ {h}h{m:02d}" if m else f"⏱ {h}h")
        stats_line = " &nbsp;·&nbsp; ".join(parts)
        diff_badge = (
            f'<span style="background:{diff_color};color:white;border-radius:3px;'
            f'padding:1px 5px;font-size:10px;font-weight:700;margin-right:4px">'
            f'{(difficulty or "").upper()}</span>'
        ) if difficulty else ""
        extra_rows += (
            f'<div style="margin-top:6px;padding:5px 7px;background:#f4f8ff;'
            f'border-radius:4px;font-size:11px;color:#444">'
            f'{diff_badge}{stats_line}</div>'
        )
        if alltrails_url:
            extra_rows += (
                f'<div style="margin-top:4px;font-size:11px">'
                f'<a href="{alltrails_url}" target="_blank" '
                f'style="color:#00b050;text-decoration:none;font-weight:600">'
                f'🥾 Find trails on AllTrails ↗</a></div>'
            )

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


def _e(text: str | None) -> str:
    """HTML-escape a string safely."""
    return html_lib.escape(str(text or ""))


def build_itinerary_panel(data: dict) -> str:
    """Return the full HTML/CSS/JS for the itinerary side panel and toggle button."""

    trip_name    = _e(data.get("trip_name", "Trip"))
    country      = _e(data.get("country", ""))
    region       = _e(data.get("region", ""))
    location_line = ", ".join(filter(None, [region, country]))

    # ── Accommodations section ────────────────────────────────────────────
    acc_items = ""
    for acc in data.get("accommodations", []):
        stars    = int(acc.get("stars") or 0)
        stars_s  = ("★" * stars + "☆" * (5 - stars)) if stars else ""
        amenities = _e(acc.get("amenities") or "")
        ci = acc.get("check_in_day", "?")
        co = acc.get("check_out_day", "?")
        acc_items += f"""
        <div style="padding:8px 0;border-bottom:1px solid #f0f0f0">
          <div style="font-weight:bold">🏨 {_e(acc['name'])}
            <span style="color:#f0a500;font-size:11px;margin-left:4px">{stars_s}</span>
          </div>
          <div style="font-size:11px;color:#888">Check-in Day {ci} · Check-out Day {co}</div>
          <div style="font-size:12px;color:#555;margin-top:2px">{_e(acc.get('description',''))}</div>
          {"<div style='font-size:11px;color:#888;margin-top:2px'>🏷 " + amenities + "</div>" if amenities else ""}
        </div>"""

    acc_section = f"""
    <div style="margin-bottom:16px">
      <div style="font-weight:bold;font-size:13px;margin-bottom:6px;
                  padding-bottom:4px;border-bottom:2px solid #2c3e50">🏨 Accommodations</div>
      {acc_items if acc_items else '<div style="color:#aaa;font-size:12px">None listed</div>'}
    </div>""" if data.get("accommodations") else ""

    # ── Day sections ──────────────────────────────────────────────────────
    days_html = ""
    for i, day in enumerate(data.get("days", [])):
        color     = DAY_COLORS[i % len(DAY_COLORS)]
        day_label = _e(day.get("label") or f"Day {day['day_number']}")
        date_s    = _e(day.get("date") or "")

        locs_html = ""
        for loc in sorted(day.get("locations", []), key=lambda x: x.get("order", 99)):
            loc_type = loc.get("type", "default")
            if loc_type == "transport":
                mode  = (loc.get("transport_mode") or "train").lower()
                emoji = TRANSPORT_MODE_EMOJI.get(mode, "🚆")
            else:
                emoji = TYPE_EMOJI.get(loc_type, TYPE_EMOJI["default"])

            highlights = _e(loc.get("highlights") or "")
            tips       = _e(loc.get("tips") or "")
            cuisine    = _e(loc.get("cuisine") or "")
            price      = _e(loc.get("price_range") or "")
            route      = loc.get("_route_to_next")
            trail_km   = loc.get("trail_distance_km")
            elev       = loc.get("elevation_gain_m")
            diff       = _e((loc.get("difficulty") or "").strip())
            dur_h      = loc.get("duration_hours")

            cuisine_line = ""
            if cuisine:
                cuisine_line = f'<span style="color:#888">🍴 {cuisine}'
                if price:
                    cuisine_line += f" · {price}"
                cuisine_line += "</span>"

            # Hiking stats line
            hiking_line = ""
            if any(v is not None for v in (trail_km, elev, dur_h)) or diff:
                diff_color = {"easy": "#27ae60", "moderate": "#e67e22",
                              "hard": "#e74c3c", "expert": "#8e44ad"}.get(
                    diff.lower(), "#777"
                )
                hparts = []
                if trail_km is not None:
                    hparts.append(f"📏 {trail_km} km")
                if elev is not None:
                    hparts.append(f"⬆ {elev} m gain")
                if dur_h is not None:
                    hh, mm = int(dur_h), round((dur_h - int(dur_h)) * 60)
                    hparts.append(f"⏱ {hh}h{mm:02d}" if mm else f"⏱ {hh}h")
                diff_badge = (
                    f'<span style="background:{diff_color};color:white;'
                    f'border-radius:3px;padding:1px 4px;font-size:10px;'
                    f'font-weight:700;margin-right:4px">{diff.upper()}</span>'
                ) if diff else ""
                at_q  = urllib.parse.quote(f"{loc['name']} {data.get('region','')} {data.get('country','')}")
                at_url = f"https://www.alltrails.com/explore?q={at_q}"
                hiking_line = (
                    f'<div style="font-size:11px;background:#f0f7f0;border-radius:3px;'
                    f'padding:4px 6px;margin-top:4px">'
                    f'{diff_badge}{" &nbsp;·&nbsp; ".join(hparts)}'
                    f'&nbsp;&nbsp;<a href="{at_url}" target="_blank" '
                    f'style="color:#00b050;font-weight:600;text-decoration:none">'
                    f'🥾 AllTrails</a></div>'
                )

            route_line = ""
            if route and route.get("km", 0) >= 0.05:
                km     = route["km"]
                mins   = route["drive_mins"]
                raw_n  = route.get("next_name", "next stop")
                next_n = _e(raw_n[:33] + "…" if len(raw_n) > 35 else raw_n)
                if km < 1.5:
                    travel = f"🚶 {max(round(km/0.08), 1)} min walk"
                else:
                    travel = f"🚗 {mins} min · 🚇 ~{round(mins*1.35)} min"
                route_line = (
                    f'<div style="font-size:11px;color:#999;margin-top:3px">'
                    f'→ To {next_n}: {km} km | {travel}</div>'
                )

            locs_html += f"""
            <div style="padding:7px 0 7px 10px;border-left:3px solid {color};
                        margin-bottom:6px;background:#fafafa;border-radius:0 4px 4px 0">
              <div style="font-weight:600;font-size:13px">{emoji} {_e(loc['name'])}</div>
              <div style="font-size:12px;color:#555;margin-top:2px">{_e(loc.get('description',''))}</div>
              {"<div style='font-size:11px;color:#2c7;margin-top:3px'>✨ " + highlights + "</div>" if highlights else ""}
              {"<div style='font-size:11px;color:#27ae60;margin-top:2px'>💡 " + tips + "</div>" if tips else ""}
              {"<div style='font-size:11px;margin-top:2px'>" + cuisine_line + "</div>" if cuisine_line else ""}
              {hiking_line}
              {route_line}
            </div>"""

        days_html += f"""
        <div style="margin-bottom:18px">
          <div style="background:{color};color:white;padding:6px 10px;border-radius:5px;
                      font-weight:bold;font-size:13px;margin-bottom:8px">
            {day_label}{(' <span style="font-weight:normal;opacity:.85;font-size:11px">· ' + date_s + '</span>') if date_s else ''}
          </div>
          {locs_html}
        </div>"""

    # ── Full panel HTML + toggle button ───────────────────────────────────
    return f"""
    <!-- Itinerary toggle button -->
    <div id="itin-btn"
         onclick="document.getElementById('itin-panel').style.display='flex';
                  document.getElementById('itin-btn').style.display='none'"
         title="Show full itinerary"
         style="position:fixed;top:90px;left:10px;z-index:9999;
                background:#2c3e50;color:white;border-radius:6px;
                padding:8px 12px;cursor:pointer;font-size:13px;
                box-shadow:2px 2px 6px rgba(0,0,0,.35);
                font-family:Arial,sans-serif;user-select:none">
      📋 Itinerary
    </div>

    <!-- Itinerary side panel -->
    <div id="itin-panel"
         style="display:none;position:fixed;top:0;right:0;height:100%;width:390px;
                z-index:10000;background:white;
                box-shadow:-4px 0 16px rgba(0,0,0,.2);
                flex-direction:column;font-family:Arial,sans-serif">

      <!-- Panel header -->
      <div style="background:#2c3e50;color:white;padding:14px 16px;flex-shrink:0">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-size:16px;font-weight:bold">{trip_name}</div>
            {"<div style='font-size:12px;opacity:.8;margin-top:2px'>📍 " + location_line + "</div>" if location_line else ""}
          </div>
          <div onclick="document.getElementById('itin-panel').style.display='none';
                        document.getElementById('itin-btn').style.display='block'"
               style="cursor:pointer;font-size:20px;line-height:1;padding:0 4px;opacity:.8"
               title="Close">✕</div>
        </div>
      </div>

      <!-- Scrollable content -->
      <div style="overflow-y:auto;padding:16px;flex:1">
        {acc_section}
        {days_html}
      </div>
    </div>"""


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

    m = folium.Map(location=center, zoom_start=7, tiles=None)

    # Google Maps road view (default)
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="Google Maps",
        overlay=False,
        control=True,
        show=True,
    ).add_to(m)

    # Google Satellite + labels
    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Satellite",
        name="Google Satellite",
        overlay=False,
        control=True,
        show=False,
    ).add_to(m)

    # Auto-fit zoom to the actual travel area
    if min_lat is not None:
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=[40, 40])

    accommodations = data.get("accommodations", [])

    def morning_hotel(day_num: int) -> dict | None:
        """Hotel the traveller WAKES UP IN on day_num (slept there night day_num-1→day_num)."""
        for acc in accommodations:
            ci = acc.get("check_in_day") or 0
            co = acc.get("check_out_day") or 0
            if ci < day_num <= co and acc.get("_coords"):
                return acc
        return None

    def night_hotel(day_num: int) -> dict | None:
        """Hotel the traveller SLEEPS IN tonight (night day_num→day_num+1)."""
        for acc in accommodations:
            ci = acc.get("check_in_day") or 0
            co = acc.get("check_out_day") or 0
            if ci <= day_num < co and acc.get("_coords"):
                return acc
        return None

    def hotel_already_in_locs(hotel: dict, locs: list) -> bool:
        """True if the hotel name appears in the day's location list."""
        h = hotel["name"].lower()
        return any(h in loc["name"].lower() or loc["name"].lower() in h for loc in locs)

    # ── Per-day layers ────────────────────────────────────────────────────
    for i, day in enumerate(data.get("days", [])):
        color      = DAY_COLORS[i % len(DAY_COLORS)]
        day_label  = day.get("label") or f"Day {day['day_number']}"
        fg         = folium.FeatureGroup(name=f"📅 {day_label}", show=True)
        day_coords: list[tuple[float, float]] = []
        route_segments: list[str] = []

        sorted_locs = sorted(day.get("locations", []), key=lambda x: x.get("order", 99))
        stop_num = 0  # resets to 1 for each day's first attraction

        # ── Overnight hotel as day start ──────────────────────────────────
        hotel = morning_hotel(day["day_number"])
        if hotel and not hotel_already_in_locs(hotel, sorted_locs):
            hc = hotel["_coords"]
            day_coords.append(hc)
            stars   = int(hotel.get("stars") or 0)
            stars_s = "★" * stars if stars else ""
            ci, co  = hotel.get("check_in_day", "?"), hotel.get("check_out_day", "?")

            hotel_marker_html = f"""
            <div style="position:relative;width:40px;height:40px">
              <div style="background:white;border-radius:50%;width:34px;height:34px;
                          text-align:center;line-height:34px;font-size:18px;
                          border:3px dashed {color};
                          box-shadow:0 2px 5px rgba(0,0,0,.35)">🏨</div>
              <div style="position:absolute;bottom:-3px;right:-3px;font-size:13px
                          ;line-height:1">🌙</div>
            </div>"""

            folium.Marker(
                location=hc,
                popup=_popup_html(
                    f"🏨 {hotel['name']}",
                    f"Overnight · Day {day['day_number']} start  {stars_s}",
                    hotel.get("description", ""),
                    amenities = hotel.get("amenities"),
                    image_url = hotel.get("_image_url"),
                ),
                tooltip=f"🌙 Day {day['day_number']} starts here — {hotel['name']}",
                icon=folium.DivIcon(
                    html=hotel_marker_html,
                    icon_size=(40, 40),
                    icon_anchor=(19, 36),
                ),
            ).add_to(fg)

        for loc in sorted_locs:
            coords = loc.get("_coords")
            if not coords:
                continue
            day_coords.append(coords)

            loc_type  = loc.get("type", "default")
            emoji     = TYPE_EMOJI.get(loc_type, TYPE_EMOJI["default"])
            if loc_type == "transport":
                mode  = (loc.get("transport_mode") or "train").lower()
                emoji = TRANSPORT_MODE_EMOJI.get(mode, "🚆")
            route_nxt = loc.get("_route_to_next")

            if route_nxt:
                route_segments.append(
                    f"{loc['name']} → next: {route_nxt['km']} km, "
                    f"{route_nxt['drive_mins']} min drive"
                )

            if loc_type == "hotel":
                # Hotel stop in the daily itinerary — use hotel marker, no number
                marker_html = f"""
                <div style="position:relative;width:40px;height:40px">
                  <div style="background:white;border-radius:50%;width:34px;height:34px;
                              text-align:center;line-height:34px;font-size:18px;
                              border:3px dashed {color};
                              box-shadow:0 2px 5px rgba(0,0,0,.35)">🏨</div>
                </div>"""
                folium.Marker(
                    location=coords,
                    popup=_popup_html(
                        f"🏨 {loc['name']}",
                        f"Day {day['day_number']} · Hotel",
                        loc.get("description", ""),
                        highlights = loc.get("highlights"),
                        tips       = loc.get("tips"),
                        image_url  = loc.get("_image_url"),
                        route      = route_nxt,
                    ),
                    tooltip=f"🏨 Day {day['day_number']}: {loc['name']}",
                    icon=folium.DivIcon(
                        html=marker_html,
                        icon_size=(40, 40),
                        icon_anchor=(19, 36),
                    ),
                ).add_to(fg)
            else:
                stop_num += 1
                # Build AllTrails search URL for hiking/activity types
                _at_url = None
                if loc_type in ("activity",) and loc.get("trail_distance_km") is not None:
                    _q = urllib.parse.quote(
                        f"{loc['name']} {data.get('region', '')} {data.get('country', '')}"
                    )
                    _at_url = f"https://www.alltrails.com/explore?q={_q}"

                # Emoji circle marker + global number badge in top-right corner
                marker_html = f"""
                <div style="position:relative;width:40px;height:40px">
                  <div style="background:{color};border-radius:50%;width:34px;height:34px;
                              text-align:center;line-height:34px;font-size:18px;
                              border:2px solid white;
                              box-shadow:0 2px 6px rgba(0,0,0,.45)">{emoji}</div>
                  <div style="position:absolute;top:-4px;right:-2px;
                              background:white;color:{color};border:2px solid {color};
                              border-radius:50%;width:17px;height:17px;
                              text-align:center;line-height:15px;font-size:10px;
                              font-weight:bold;box-shadow:0 1px 3px rgba(0,0,0,.3)">{stop_num}</div>
                </div>"""
                folium.Marker(
                    location=coords,
                    popup=_popup_html(
                        f"{emoji} {loc['name']}",
                        f"Day {day['day_number']} · #{stop_num} · {loc_type.title()}",
                        loc.get("description", ""),
                        highlights        = loc.get("highlights"),
                        tips              = loc.get("tips"),
                        cuisine           = loc.get("cuisine"),
                        price_range       = loc.get("price_range"),
                        image_url         = loc.get("_image_url"),
                        route             = route_nxt,
                        trail_distance_km = loc.get("trail_distance_km"),
                        elevation_gain_m  = loc.get("elevation_gain_m"),
                        difficulty        = loc.get("difficulty"),
                        duration_hours    = loc.get("duration_hours"),
                        alltrails_url     = _at_url,
                    ),
                    tooltip=f"#{stop_num}  {loc['name']}",
                    icon=folium.DivIcon(
                        html=marker_html,
                        icon_size=(40, 40),
                        icon_anchor=(19, 36),
                    ),
                ).add_to(fg)

        # Route line with direction arrows
        if len(day_coords) >= 2:
            total_km   = sum(s.get("km", 0) for s in
                             [l.get("_route_to_next") or {} for l in sorted_locs if l.get("_coords")])
            total_mins = sum(s.get("drive_mins", 0) for s in
                             [l.get("_route_to_next") or {} for l in sorted_locs if l.get("_coords")])
            line_tip   = day_label
            if total_km:
                line_tip += f" — {round(total_km, 1)} km total, ~{total_mins} min drive"

            pl = folium.PolyLine(
                locations=day_coords,
                color=color,
                weight=4,
                opacity=0.85,
                tooltip=line_tip,
            )
            pl.add_to(fg)
            PolyLineTextPath(
                pl,
                "                         ▶                         ",
                repeat=True,
                offset=8,
                attributes={"fill": color, "font-size": "16", "font-weight": "bold",
                            "opacity": "0.75"},
            ).add_to(fg)

        fg.add_to(m)

    # ── Accommodations layer ──────────────────────────────────────────────
    acc_fg = folium.FeatureGroup(name="🏨 Accommodations", show=True)
    for acc in data.get("accommodations", []):
        coords = acc.get("_coords")
        if not coords:
            continue
        ci    = acc.get("check_in_day",  "?")
        co    = acc.get("check_out_day", "?")
        stars = int(acc.get("stars") or 0)
        stars_s = "★" * stars if stars else ""

        # Offset slightly north so it doesn't overlap day-route markers
        offset_coords = (coords[0] + 0.0003, coords[1])

        acc_marker_html = f"""
        <div style="display:inline-block;text-align:center">
          <div style="background:#154360;color:white;border-radius:8px;
                      padding:5px 8px;font-size:16px;border:2px solid white;
                      box-shadow:0 3px 7px rgba(0,0,0,.45);line-height:1.2">
            🏨
            <div style="font-size:9px;font-weight:bold;letter-spacing:.5px;
                        opacity:.9">{stars_s or "HOTEL"}</div>
          </div>
          <div style="width:0;height:0;border-left:7px solid transparent;
                      border-right:7px solid transparent;
                      border-top:8px solid #154360;margin:0 auto"></div>
        </div>"""

        folium.Marker(
            location=offset_coords,
            popup=_popup_html(
                f"🏨 {acc['name']}",
                f"Check-in: Day {ci}  ·  Check-out: Day {co}",
                acc.get("description", ""),
                stars     = acc.get("stars"),
                amenities = acc.get("amenities"),
                image_url = acc.get("_image_url"),
            ),
            tooltip=f"🏨 {acc['name']}  {stars_s}  (Days {ci}–{co})",
            icon=folium.DivIcon(
                html=acc_marker_html,
                icon_size=(60, 52),
                icon_anchor=(30, 52),
            ),
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

    # ── Itinerary panel ───────────────────────────────────────────────────
    m.get_root().html.add_child(folium.Element(build_itinerary_panel(data)))

    # ── Layer control ─────────────────────────────────────────────────────
    folium.LayerControl(collapsed=False).add_to(m)

    return m


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Visualise a trip description as an interactive map.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python trip_visualizer.py my_trip.txt\n"
            "  python trip_visualizer.py --plan\n"
            "  python trip_visualizer.py my_trip.txt -o map.html --json-output parsed.json"
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to trip text file, or '-' to read from stdin. Omit when using --plan.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Interactively plan a nature trip with Vacation Trip Planner, then map it.",
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

    # Read or generate trip text
    if args.plan:
        text = run_nature_planner(api_key=args.api_key)
    elif args.input:
        if args.input == "-":
            print("Reading from stdin…", file=sys.stderr)
            text = sys.stdin.read()
        else:
            path = Path(args.input)
            if not path.exists():
                print(f"Error: file not found — {path}", file=sys.stderr)
                sys.exit(1)
            text = path.read_text(encoding="utf-8")
    else:
        parser.error("Provide an input file or use --plan for interactive trip planning.")

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
