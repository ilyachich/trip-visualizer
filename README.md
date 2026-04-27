# Trip Visualizer & Vacation Trip Planner

Turn any free-text trip description into an interactive map — day by day, completely free.
Or use the **Streamlit web app** to plan a trip from scratch with AI.

---

## Two ways to use it

### 1. Streamlit Web App — plan a trip with AI

Run the interactive planner in your browser:

```
streamlit run app.py
```

- Fill in ~20 travel preferences (destination, dates, pace, budget, accommodation, food, hiking level, …)
- AI (Groq / Llama 3.3 70B) generates a structured JSON itinerary in a **single call** — the same data drives both the displayed plan and the map, so they are always in sync
- At least 5 locations per day guaranteed: hotel + activities + restaurants + sights
- Day 1 always includes arrival city attractions so it appears on the map from the start
- Hiking trips get full trail details: distance, elevation gain, difficulty and an AllTrails search link
- An animated SVG airplane flies across the screen while the map is built
- Get a colour-coded interactive map + structured itinerary ready to download

**Requirements:** set `GROQ_API_KEY` in environment or Streamlit secrets.

### 2. CLI — visualise an existing trip description

Paste your trip notes into a text file and get a map:

```
python trip_visualizer.py my_trip.txt
python trip_visualizer.py my_trip.txt -o paris.html
python trip_visualizer.py my_trip.txt -o paris.html --json-output parsed.json
```

---

## What the map includes

- **Per-day colour-coded routes** — numbered stops (1, 2, 3… reset each day) with direction arrows
- **Hotel-first routing** — each day starts at the overnight hotel (🌙), then visits attractions in order
- **Typed markers** — 🏨 hotels, 🍴 restaurants, 🎯 activities, 🏛️ sights, ✈️ airports, 🚂 trains, 🚌 buses, 🚇 metro, 🚢 ships
- **Accommodation layer** — hotel badge markers with stars, check-in/out days (offset to avoid overlap)
- **Distances & travel times** — "To [Place]: X km | 🚗 12 min" between every stop
- **Place photos** — Wikipedia thumbnail in every popup
- **Hiking popup cards** — trail distance, elevation gain, duration, colour-coded difficulty badge (easy / moderate / hard / expert) and an AllTrails search link
- **Rich popups** — highlights, practical tips, cuisine, price range, hotel stars and amenities
- **Itinerary panel** — left-side button opens a full side panel with the complete trip; hiking entries show stats and AllTrails link
- **Google Maps base layer** — road map by default, switchable to satellite
- **Auto-zoom** — map fits exactly to the travel area

---

## Hiking support

When the trip type includes hiking or trekking, the AI generates:

| Field | Example |
|---|---|
| Trail name | "Triglav Summit Trail via Kredarica Hut" |
| Distance | 📏 16 km |
| Elevation gain | ⬆ 1 800 m |
| Duration | ⏱ 9h |
| Difficulty | **HARD** (colour-coded badge) |
| Trail link | 🥾 AllTrails ↗ (opens search for that trail) |

These appear in the map popup, the in-map itinerary panel, and the Streamlit itinerary.

---

## Cost

| Service | Cost |
|---|---|
| Groq / Llama 3.3 70B (AI planning) | Free |
| OpenStreetMap / Nominatim geocoding | Free |
| OSRM routing (distances & times) | Free |
| Wikipedia images | Free |
| AllTrails links | Free (search URL, no API key) |
| Folium map rendering | Free |
| **Total** | **$0** |

---

## Setup

### 1. Install dependencies

```
pip install -r requirements.txt
```

or manually:

```
pip install folium groq requests streamlit
```

### 2. Get a free Groq API key

Go to **https://console.groq.com** → sign in → API Keys → Create API key.

### 3. Save the key

**Windows:**
```
setx GROQ_API_KEY "your-key-here"
```

**Mac / Linux:**
```
export GROQ_API_KEY="your-key-here"
```

Open a new terminal after running `setx` on Windows.

---

## CLI arguments

| Argument | Description |
|---|---|
| `my_trip.txt` | Your trip description (plain text) |
| `-o output.html` | Where to save the map (default: `trip_map.html`) |
| `--json-output file.json` | Also save the parsed itinerary as JSON |
| `--api-key KEY` | Pass the Groq API key directly instead of env var |

---

## How it works

1. **Plan** *(web app only)* — a single Groq call turns your 20-question form into structured JSON with at least 5 locations per day; hiking entries include trail stats
2. **Geocode** — each place is resolved to coordinates using a 5-level fallback chain: full address with country → full address without country filter → name + country → city + country → bare name with type words stripped. If all attempts fail the pin is placed at city level so every planned stop always appears on the map
3. **Route** — OSRM calculates driving distance and time between consecutive stops each day
4. **Images** — Wikipedia search API finds thumbnails for each location
5. **Render** — Folium builds an interactive Leaflet.js map saved as a self-contained HTML file that works offline in any browser

---

## Map controls

| Control | Description |
|---|---|
| 📋 Itinerary | Opens full trip description panel (left-side button, below zoom controls) |
| Layer control | Toggle individual days and accommodation layer on/off |
| Legend | Shows trip name, region, day colours and marker types |
| Marker click | Opens popup with photo, description, highlights, tips, hiking stats and distance to next stop |
| Route line hover | Shows day label and total distance |
| 🌙 marker | Hotel where the day starts (overnight stay) |
| 🥾 AllTrails ↗ | Link inside hiking activity popups — opens AllTrails search for that trail |
