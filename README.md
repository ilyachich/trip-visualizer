# Trip Visualizer

Turn any free-text trip description into an interactive map — day by day, completely free.

## What it does

Paste your trip notes (hotels, restaurants, sights, day by day) and get back a single HTML file you can open in any browser:

- **Per-day colour-coded routes** — numbered stops (1, 2, 3…) with direction arrows showing travel order
- **Typed markers** — 🏨 hotels, 🍴 restaurants, 🎯 activities, 🏛️ sights, ✈️ airports, 🚂 trains, 🚌 buses, 🚇 metro, 🚢 ships
- **Overnight hotel as day start** — each day's route begins at the hotel where you slept (🌙 marker), even if not explicitly in the text
- **Return-to-hotel line** — route closes back to the night's hotel at the end of each day
- **Accommodation layer** — hotel badge markers (offset to avoid overlap) with stars, check-in/out days
- **Distances & travel times** — "To [Place]: X km | 🚗 12 min · 🚇 ~16 min" between every stop
- **Place photos** — Wikipedia thumbnail in every popup, click to enlarge
- **Rich popups** — highlights, practical tips, cuisine, price range, hotel stars and amenities
- **📋 Itinerary panel** — left-side button opens a full side panel with the complete trip day by day
- **Google Maps base layer** — road map by default, switchable to Google Satellite
- **Auto-zoom** — map fits exactly to the travel area
- **Country-aware geocoding** — restricts search to the correct country, preventing wrong-location matches
- **Region & country** in the legend

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

1. **Parse** — Groq (Llama 3.3 70B) reads your text and extracts days, locations, transport modes, accommodations, highlights, tips, cuisine, hotel stars, and more
2. **Geocode** — Each place is looked up on OpenStreetMap, restricted to the correct country
3. **Route** — OSRM calculates driving distance and time between consecutive stops each day
4. **Images** — Wikipedia search API finds thumbnails for each location
5. **Render** — Folium builds an interactive Leaflet.js map saved as a self-contained HTML file

## Map controls

| Control | Description |
|---|---|
| 📋 Itinerary | Opens full trip description panel (left-side button, below zoom controls) |
| Layer control | Toggle individual days and accommodation layer on/off |
| Legend | Shows trip name, region, day colours and marker types |
| Marker click | Opens popup with photo, description, highlights, tips and distance to next stop |
| Route line hover | Shows day label and total distance |
| 🌙 marker | Hotel where the day starts (overnight stay) |
