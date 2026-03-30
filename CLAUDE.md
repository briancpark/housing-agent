# CLAUDE.md

## Project Overview

Housing Agent is a South Bay Area housing search tool. It scrapes Redfin listings, calculates mortgage estimates, and shows results on an interactive Leaflet.js map.

## Architecture

- **`scraper.py`** — Main scraper. Uses Redfin's `gis-csv` endpoint (not the autocomplete API, which blocks bots). Region IDs are hardcoded in `SOUTH_BAY_CITIES`. Outputs both CSV and JSON (`web/data/listings.json`).
- **`mortgage_calc.py`** — Standalone CLI mortgage calculator. No shared code with `scraper.py` (each has its own mortgage math).
- **`web/index.html`** — Single-file SPA. No build step, no framework. Uses Leaflet.js + CARTO dark tiles via CDN. Reads `data/listings.json` at load time.

## Key Technical Details

- Redfin's autocomplete API (`/stingray/do/location-autocomplete`) returns 403 for automated requests. The `gis-csv` endpoint works fine with just a User-Agent header.
- Region IDs are specific to Redfin and won't change. They map city names to numeric IDs (e.g., San Jose = 17420).
- The scraper adds a 2-second delay between cities to be polite to Redfin's servers.
- Listings are deduplicated by lowercase address since cities can overlap in Redfin's results.
- The web app recalculates mortgages client-side when the user changes settings — it doesn't re-fetch data.

## Commands

```bash
# Run scraper (generates CSV + JSON)
source venv/bin/activate && python scraper.py

# Run mortgage calculator
python mortgage_calc.py 1200000        # quick mode
python mortgage_calc.py                # interactive mode

# Serve web app
cd web && python -m http.server 8000
```

## Dependencies

Python: `requests`, `beautifulsoup4`, `pandas`, `lxml` (see `requirements.txt`). The `beautifulsoup4`, `pandas`, and `lxml` packages are installed but not currently used by the scraper — they're available for future HTML parsing needs.

Web: Leaflet.js, Leaflet.markercluster, CARTO tiles (all loaded via CDN in `index.html`).

## File Conventions

- Generated data files (`.csv`, `.json`) are gitignored
- `web/data/` directory is created automatically by the scraper
- No `.env` or API keys needed — Redfin's endpoint and OpenStreetMap tiles are free/public
