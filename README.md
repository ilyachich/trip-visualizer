# Trip Visualizer

Turn any free-text trip description into an interactive map — day by day, completely free.

## What it does

Paste your trip notes (hotels, restaurants, sights, day by day) and get back a single HTML file you can open in any browser:

- **Per-day colour-coded routes** connecting all stops in order
- **Typed markers with correct icons** — 🛏 hotels, 🍴 restaurants, 📷 activities, 📍 sights, ✈️ airports, 🚂 trains, 🚌 buses, 🚇 metro, 🚢 ships
- **Distances & travel times** — shows "To [Place]: X km | 🚗 12 min · 🚇 ~16 min" between every stop
- **Place photos** — Wikipedia thumbnail in every popup, click to enlarge
- **Rich popups** — highlights, practical tips, cuisine type, price range, hotel star rating and amenities
- **📋 Itinerary panel** — floating button opens a full side panel with the complete trip description day by day, including all stops, tips, distances and accommodation details
- **Auto-zoom** — map fits exactly to the travel area (no whole-continent view)
- **Country-aware geocoding** — locations restricted to the correct country, preventing wrong-country matches
- **Region & country** displayed in the legend
- **Accommodation layer** showing every hotel with check-in / check-out days
- Clickable popups, toggleable layers, built-in legend

## Cost

| Service | Cost |
|---|---|
| Groq / Llama 3.3 70B (AI parsing) | Free |
| OpenStreetMap geocoding | Free |
| OSRM routing (distances & times) | Free |
| Wikipedia images | Free |
| Folium map rendering | Free |
| **Total** | **$0** |

## Setup

### 1. Install Python dependencies

```
pip install folium groq requests
```

### 2. Get a free Groq API key

Go to **https://console.groq.com** → sign in → API Keys → Create API key.

### 3. Save the key (Windows)

```
setx GROQ_API_KEY "your-key-here"
```

Open a new terminal after running this.

## Usage

```
python trip_visualizer.py my_trip.txt
python trip_visualizer.py my_trip.txt -o paris.html
python trip_visualizer.py my_trip.txt -o paris.html --json-output parsed.json
```

### Arguments

| Argument | Description |
|---|---|
| `my_trip.txt` | Your trip description (plain text) |
| `-o output.html` | Where to save the map (default: `trip_map.html`) |
| `--json-output file.json` | Also save the parsed itinerary as JSON |
| `--api-key KEY` | Pass the Groq API key directly instead of env var |

## Example input

See [example_trip.txt](example_trip.txt) for a sample 7-day Japan itinerary.

## How it works

1. **Parse** — Groq (Llama 3.3 70B) reads your text and extracts a structured list of days, locations, transport modes, accommodations, highlights, tips, cuisine, hotel stars, and more
2. **Geocode** — Each place is looked up on OpenStreetMap, restricted to the correct country to avoid wrong-country matches
3. **Route** — OSRM calculates driving distance and time between consecutive stops each day
4. **Images** — Wikipedia search API finds thumbnails for each location
5. **Render** — Folium builds an interactive Leaflet.js map and saves it as a self-contained HTML file

## Map controls

| Control | Description |
|---|---|
| 📋 Itinerary | Opens full trip description panel (top-right button) |
| Layer control | Toggle individual days and accommodation layer on/off |
| Legend | Shows trip name, region, day colours and marker types |
| Marker click | Opens popup with photo, description, highlights, tips and distance to next stop |
| Route line hover | Shows day label and total distance |
