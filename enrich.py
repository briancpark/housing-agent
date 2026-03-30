#!/usr/bin/env python3
"""
Enrich housing listings with Walk Score data and OSRM commute times to Apple Park.

Data sources:
  1. Walk Score (walkscore.com) - Walk, Transit, and Bike scores
  2. OSRM (Open Source Routing Machine) - Driving commute time/distance to Apple Park

Usage:
  python enrich.py                  # Enrich all listings
  python enrich.py --limit 3        # Enrich only the first 3 listings (for testing)
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Apple Park coordinates
APPLE_PARK_LAT = 37.3349
APPLE_PARK_LNG = -122.0089

OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
WALKSCORE_BASE_URL = "https://www.walkscore.com/score"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

LISTINGS_PATH = Path(__file__).parent / "web" / "data" / "listings.json"
ENRICHED_PATH = Path(__file__).parent / "web" / "data" / "listings_enriched.json"

METERS_PER_MILE = 1609.34

# City-level crime grades from AreaVibes (fetched March 2026)
# Grades reflect overall crime compared to national average
CITY_CRIME_GRADES = {
    "Cupertino":      {"grade": "A-", "violent_vs_national": -69, "property_vs_national": -11},
    "Saratoga":       {"grade": "A",  "violent_vs_national": -80, "property_vs_national": -30},
    "Los Gatos":      {"grade": "B+", "violent_vs_national": -55, "property_vs_national": -5},
    "Sunnyvale":      {"grade": "C+", "violent_vs_national": -32, "property_vs_national": +8},
    "Santa Clara":    {"grade": "C+", "violent_vs_national": -49, "property_vs_national": +42},
    "Palo Alto":      {"grade": "C",  "violent_vs_national": -41, "property_vs_national": +72},
    "Mountain View":  {"grade": "D+", "violent_vs_national": -15, "property_vs_national": +58},
    "Milpitas":       {"grade": "D",  "violent_vs_national": -13, "property_vs_national": +81},
    "San Jose":       {"grade": "F",  "violent_vs_national": +51, "property_vs_national": +51},
    "Campbell":       {"grade": "F",  "violent_vs_national": +36, "property_vs_national": +68},
    "East Palo Alto": {"grade": "F",  "violent_vs_national": +100, "property_vs_national": +50},
    "Los Altos":      {"grade": "A",  "violent_vs_national": -75, "property_vs_national": -20},
    "Morgan Hill":    {"grade": "C",  "violent_vs_national": -20, "property_vs_national": +40},
    "Fremont":        {"grade": "C+", "violent_vs_national": -30, "property_vs_national": +15},
}


def make_address_slug(address: str, city: str, state: str, zip_code: str) -> str:
    """
    Convert an address into the walkscore.com URL slug format.

    Example: "3029 Kaiser Dr Unit A", "Santa Clara", "CA", "95051"
           -> "3029-kaiser-dr-unit-a-santa-clara-ca-95051"
    """
    parts = f"{address} {city} {state} {zip_code}"
    # Lowercase, replace # with empty (walkscore drops it), then non-alphanum to dash
    slug = parts.lower()
    slug = slug.replace("#", "")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def fetch_osrm_commute(lat: float, lng: float) -> dict:
    """
    Fetch driving commute time and distance from (lat, lng) to Apple Park via OSRM.

    Returns dict with commute_minutes and commute_distance_miles, or nulls on error.
    """
    result = {"commute_minutes": None, "commute_distance_miles": None}

    if lat is None or lng is None:
        return result

    url = (
        f"{OSRM_BASE_URL}/{lng},{lat};{APPLE_PARK_LNG},{APPLE_PARK_LAT}"
        f"?overview=false"
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            duration_sec = route["duration"]
            distance_m = route["distance"]
            result["commute_minutes"] = round(duration_sec / 60, 1)
            result["commute_distance_miles"] = round(distance_m / METERS_PER_MILE, 1)
    except Exception as e:
        print(f"    [OSRM error] {e}")

    return result


def fetch_walkscore(address: str, city: str, state: str, zip_code: str) -> dict:
    """
    Fetch Walk Score, Transit Score, and Bike Score from walkscore.com.

    Parses the badge SVG URLs which follow the pattern:
      //pp.walk.sc/badge/walk/score/{N}.svg
      //pp.walk.sc/badge/transit/score/{N}.svg
      //pp.walk.sc/badge/bike/score/{N}.svg

    Returns dict with walk_score, transit_score, bike_score (or nulls on error).
    """
    result = {"walk_score": None, "transit_score": None, "bike_score": None}

    slug = make_address_slug(address, city, state, zip_code)
    url = f"{WALKSCORE_BASE_URL}/{slug}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Strategy 1: Parse badge SVG URLs
        # Pattern: //pp.walk.sc/badge/{type}/score/{number}.svg
        badge_pattern = re.compile(r"pp\.walk\.sc/badge/(walk|transit|bike)/score/(\d+)\.svg")

        for img in soup.find_all("img", src=True):
            match = badge_pattern.search(img["src"])
            if match:
                score_type = match.group(1)
                score_value = int(match.group(2))
                if score_type == "walk":
                    result["walk_score"] = score_value
                elif score_type == "transit":
                    result["transit_score"] = score_value
                elif score_type == "bike":
                    result["bike_score"] = score_value

        # Strategy 2: If badges not found, try alt text on images
        if result["walk_score"] is None:
            alt_pattern = re.compile(r"^(\d+)\s+(Walk|Transit|Bike)\s+Score", re.IGNORECASE)
            for img in soup.find_all("img", alt=True):
                match = alt_pattern.match(img["alt"])
                if match:
                    score_value = int(match.group(1))
                    score_type = match.group(2).lower()
                    if score_type == "walk":
                        result["walk_score"] = score_value
                    elif score_type == "transit":
                        result["transit_score"] = score_value
                    elif score_type == "bike":
                        result["bike_score"] = score_value

        # Strategy 3: Search the raw HTML with regex as a last resort
        if result["walk_score"] is None:
            for score_type in ["walk", "transit", "bike"]:
                raw_match = badge_pattern.search(html)
                if raw_match:
                    s_type = raw_match.group(1)
                    s_val = int(raw_match.group(2))
                    key = f"{s_type}_score"
                    if key in result and result[key] is None:
                        result[key] = s_val

    except Exception as e:
        print(f"    [Walk Score error] {e}")

    return result


def get_crime_grade(city: str) -> dict:
    """Look up crime grade for a city from the hardcoded AreaVibes data."""
    result = {"crime_grade": None, "violent_vs_national": None, "property_vs_national": None}

    # Try exact match first, then fuzzy match
    data = CITY_CRIME_GRADES.get(city)
    if data is None:
        # Try matching with common prefixes stripped
        for key, val in CITY_CRIME_GRADES.items():
            if key.lower() in city.lower() or city.lower() in key.lower():
                data = val
                break

    if data:
        result["crime_grade"] = data["grade"]
        result["violent_vs_national"] = data["violent_vs_national"]
        result["property_vs_national"] = data["property_vs_national"]

    return result


def is_already_enriched(listing: dict) -> bool:
    """Check if a listing already has enrichment data (for resume support)."""
    return (
        listing.get("commute_minutes") is not None
        and listing.get("walk_score") is not None
        and listing.get("crime_grade") is not None
    )


def enrich_listings(limit: int | None = None) -> None:
    """Main enrichment loop."""
    # Load listings
    if not LISTINGS_PATH.exists():
        print(f"Error: {LISTINGS_PATH} not found.")
        sys.exit(1)

    with open(LISTINGS_PATH, "r") as f:
        listings = json.load(f)

    total = len(listings)
    if limit is not None:
        process_count = min(limit, total)
    else:
        process_count = total

    print(f"Loaded {total} listings. Will process {process_count}.")
    print()

    enriched_count = 0
    skipped_count = 0
    commute_times = []
    walk_scores = []

    for i in range(process_count):
        listing = listings[i]
        address = listing.get("address", "Unknown")
        city = listing.get("city", "")
        state = listing.get("state", "CA")
        zip_code = listing.get("zip_code", "")
        lat = listing.get("latitude")
        lng = listing.get("longitude")

        label = f"{address}, {city}"
        print(f"Enriching {i + 1}/{process_count}: {label}")

        # Resume support: skip if already enriched
        if is_already_enriched(listing):
            print(f"    Already enriched, skipping.")
            skipped_count += 1
            # Still collect stats from existing data
            if listing.get("commute_minutes") is not None:
                commute_times.append(listing["commute_minutes"])
            if listing.get("walk_score") is not None:
                walk_scores.append(listing["walk_score"])
            continue

        # Fetch OSRM commute data
        osrm_data = fetch_osrm_commute(lat, lng)
        listing.update(osrm_data)

        if osrm_data["commute_minutes"] is not None:
            commute_times.append(osrm_data["commute_minutes"])
            print(f"    Commute: {osrm_data['commute_minutes']} min, "
                  f"{osrm_data['commute_distance_miles']} miles")
        else:
            print(f"    Commute: failed to fetch")

        # Fetch Walk Score data
        ws_data = fetch_walkscore(address, city, state, zip_code)
        listing.update(ws_data)

        if ws_data["walk_score"] is not None:
            walk_scores.append(ws_data["walk_score"])
            print(f"    Walk: {ws_data['walk_score']}, "
                  f"Transit: {ws_data['transit_score']}, "
                  f"Bike: {ws_data['bike_score']}")
        else:
            print(f"    Walk Score: failed to parse")

        # Crime grade (instant — no network call)
        crime_data = get_crime_grade(city)
        listing.update(crime_data)
        if crime_data["crime_grade"]:
            print(f"    Crime grade: {crime_data['crime_grade']}")

        enriched_count += 1

        # Be polite: 1-second delay between Walk Score requests
        if i < process_count - 1:
            time.sleep(1)

    # Save enriched data back to listings.json
    with open(LISTINGS_PATH, "w") as f:
        json.dump(listings, f, indent=2)
    print(f"\nSaved enriched data to {LISTINGS_PATH}")

    # Also save a copy to listings_enriched.json
    with open(ENRICHED_PATH, "w") as f:
        json.dump(listings, f, indent=2)
    print(f"Saved copy to {ENRICHED_PATH}")

    # Print summary
    print(f"\n{'=' * 50}")
    print(f"ENRICHMENT SUMMARY")
    print(f"{'=' * 50}")
    print(f"Total listings:    {total}")
    print(f"Processed:         {process_count}")
    print(f"Newly enriched:    {enriched_count}")
    print(f"Skipped (resumed): {skipped_count}")

    if commute_times:
        avg_commute = sum(commute_times) / len(commute_times)
        print(f"Avg commute time:  {avg_commute:.1f} min ({len(commute_times)} listings)")
    else:
        print(f"Avg commute time:  N/A")

    if walk_scores:
        avg_walk = sum(walk_scores) / len(walk_scores)
        print(f"Avg walk score:    {avg_walk:.1f} ({len(walk_scores)} listings)")
    else:
        print(f"Avg walk score:    N/A")

    print(f"{'=' * 50}")


def main():
    parser = argparse.ArgumentParser(description="Enrich housing listings with commute and walkability data.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N listings (for testing)")
    args = parser.parse_args()
    enrich_listings(limit=args.limit)


if __name__ == "__main__":
    main()
