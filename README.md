# Trip Visualizer

Turn any free-text trip description into an interactive map — day by day, completely free.

![example map](https://i.imgur.com/placeholder.png)

## What it does

Paste your trip notes (hotels, restaurants, sights, day by day) and get back a single HTML file you can open in any browser:

- **Per-day colour-coded routes** connecting all stops in order
- **Typed markers** — hotels 🏨, restaurants 🍽️, activities 🎯, sights 📍, transport ✈️
- **Accommodation layer** showing every hotel with check-in / check-out days
- Clickable popups, toggleable layers, built-in legend

## Cost

| Service | Cost |
|---|---|
| Groq (AI parsing) | Free |
| OpenStreetMap geocoding | Free |
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

1. **Parse** — Groq (Llama 3.3 70B) reads your text and extracts a structured list of days, locations, and accommodations
2. **Geocode** — Each place name is looked up on OpenStreetMap to get its coordinates
3. **Render** — Folium builds an interactive Leaflet.js map and saves it as a self-contained HTML file
