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

- Fill in ~20 travel preferences (destination, dates, pace, budget, accommodation, food, …)
- AI (Groq / Llama 3.3 70B) generates a structured JSON itinerary in a single call — the same data drives both the displayed plan and the map, so they are always in sync
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
- **Rich popups** — highlights, practical tips, cuisine, price range, hotel stars and amenities
- **Itinerary panel** — left-side button opens a full side panel with the complete trip
- **Google Maps base layer** — road map by default, switchable to satellite
- **Auto-zoom** — map fits exactly to the travel area

---

## Cost

| Service | Cost |
|---|---|
| Groq / Llama 3.3 70B (AI parsing + planning) | Free |
| OpenStreetMap geocoding | Free |
| OSRM routing (distances & times) | Free |
| Wikipedia images | Free |
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

1. **Plan** *(web app only)* — Groq generates a full itinerary from your preferences
2. **Parse** — Groq (Llama 3.3 70B) extracts days, locations, transport modes, accommodations, highlights, tips, cuisine, hotel stars, and more
3. **Geocode** — Each place is resolved to coordinates using a 5-level fallback chain: full address → address without country filter → name + country → city + country → bare name (type words stripped). If all attempts fail the pin is placed at city level so every planned stop always appears on the map
4. **Route** — OSRM calculates driving distance and time between consecutive stops each day
5. **Images** — Wikipedia search API finds thumbnails for each location
6. **Render** — Folium builds an interactive Leaflet.js map saved as a self-contained HTML file

---

## Map controls

| Control | Description |
|---|---|
| 📋 Itinerary | Opens full trip description panel (left-side button, below zoom controls) |
| Layer control | Toggle individual days and accommodation layer on/off |
| Legend | Shows trip name, region, day colours and marker types |
| Marker click | Opens popup with photo, description, highlights, tips and distance to next stop |
| Route line hover | Shows day label and total distance |
| 🌙 marker | Hotel where the day starts (overnight stay) |
