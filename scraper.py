"""
South Bay Housing Scraper
Scrapes Redfin's publicly available listing data for the South Bay Area.
Outputs a CSV with listings + estimated mortgage calculations.
"""

import csv
import io
import json
import sys
import time
from dataclasses import asdict, dataclass

import requests

# ── Config ────────────────────────────────────────────────────────────────────

REDFIN_BASE = "https://www.redfin.com"

# South Bay cities with Redfin region IDs (region_type=6 = city)
SOUTH_BAY_CITIES = {
    "San Jose":       17420,
    "Sunnyvale":      19457,
    "Santa Clara":    17675,
    "Mountain View":  12739,
    "Cupertino":       4561,
    "Milpitas":       12204,
    "Campbell":        2673,
    "Los Gatos":      11234,
    "Saratoga":       17960,
    "Palo Alto":      14325,
}

# Redfin search parameters
DEFAULT_FILTERS = {
    "min_price": 500_000,
    "max_price": 2_000_000,
    "min_beds": 2,
    "max_beds": 5,
    "property_type": "house,condo,townhouse",
}

# Mortgage defaults (30-year fixed)
MORTGAGE_DEFAULTS = {
    "down_payment_pct": 0.20,  # 20% down
    "interest_rate": 0.065,     # 6.5% — update to current rate
    "loan_term_years": 30,
    "property_tax_rate": 0.012, # ~1.2% in Santa Clara County
    "insurance_annual": 1_800,  # rough estimate
    "hoa_monthly": 0,           # overridden per listing if available
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.redfin.com/",
}

OUTPUT_CSV = "south_bay_listings.csv"
OUTPUT_JSON = "web/data/listings.json"


# ── Mortgage Calculator ──────────────────────────────────────────────────────


@dataclass
class MortgageEstimate:
    home_price: float
    down_payment: float
    loan_amount: float
    monthly_principal_interest: float
    monthly_property_tax: float
    monthly_insurance: float
    monthly_hoa: float
    total_monthly_payment: float
    total_paid_over_loan: float
    total_interest_paid: float


def calculate_mortgage(
    price: float,
    down_payment_pct: float = MORTGAGE_DEFAULTS["down_payment_pct"],
    interest_rate: float = MORTGAGE_DEFAULTS["interest_rate"],
    loan_term_years: int = MORTGAGE_DEFAULTS["loan_term_years"],
    property_tax_rate: float = MORTGAGE_DEFAULTS["property_tax_rate"],
    insurance_annual: float = MORTGAGE_DEFAULTS["insurance_annual"],
    hoa_monthly: float = MORTGAGE_DEFAULTS["hoa_monthly"],
) -> MortgageEstimate:
    """Calculate monthly mortgage payment and breakdown."""
    down_payment = price * down_payment_pct
    loan_amount = price - down_payment

    # Monthly interest rate
    r = interest_rate / 12
    n = loan_term_years * 12

    # Standard amortization formula: M = P * [r(1+r)^n] / [(1+r)^n - 1]
    if r > 0:
        monthly_pi = loan_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    else:
        monthly_pi = loan_amount / n

    monthly_tax = (price * property_tax_rate) / 12
    monthly_ins = insurance_annual / 12

    total_monthly = monthly_pi + monthly_tax + monthly_ins + hoa_monthly
    total_paid = monthly_pi * n + (monthly_tax + monthly_ins + hoa_monthly) * n
    total_interest = monthly_pi * n - loan_amount

    return MortgageEstimate(
        home_price=price,
        down_payment=down_payment,
        loan_amount=loan_amount,
        monthly_principal_interest=round(monthly_pi, 2),
        monthly_property_tax=round(monthly_tax, 2),
        monthly_insurance=round(monthly_ins, 2),
        monthly_hoa=round(hoa_monthly, 2),
        total_monthly_payment=round(total_monthly, 2),
        total_paid_over_loan=round(total_paid, 2),
        total_interest_paid=round(total_interest, 2),
    )


# ── Redfin Scraper ───────────────────────────────────────────────────────────


@dataclass
class Listing:
    address: str = ""
    city: str = ""
    state: str = "CA"
    zip_code: str = ""
    price: float = 0
    beds: int = 0
    baths: float = 0
    sqft: int = 0
    price_per_sqft: float = 0
    lot_size: str = ""
    year_built: int = 0
    property_type: str = ""
    hoa: float = 0
    listing_url: str = ""
    days_on_market: int = 0
    status: str = ""
    latitude: float = 0
    longitude: float = 0
    # Mortgage fields (filled in after calculation)
    down_payment: float = 0
    monthly_mortgage: float = 0
    monthly_total: float = 0
    total_interest: float = 0


def fetch_redfin_listings(city: str, region_id: int, filters: dict) -> list[dict]:
    """
    Fetch listing data from Redfin's gis-csv endpoint.
    Uses hardcoded region IDs to bypass the autocomplete API (which blocks bots).
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    gis_url = f"{REDFIN_BASE}/stingray/api/gis-csv"
    gis_params = {
        "al": "1",
        "market": "sanfrancisco",
        "region_id": str(region_id),
        "region_type": "6",       # city
        "num_homes": "350",
        "status": "9",            # active listings
        "uipt": "1,2,3",         # house, condo, townhouse
        "sf": "1,2,3,5,6,7",
    }

    if filters.get("min_price"):
        gis_params["min_price"] = str(filters["min_price"])
    if filters.get("max_price"):
        gis_params["max_price"] = str(filters["max_price"])
    if filters.get("min_beds"):
        gis_params["min_beds"] = str(filters["min_beds"])

    try:
        resp = session.get(gis_url, params=gis_params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch listings for {city}: {e}")
        return []

    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


def parse_listing(row: dict, city: str) -> Listing | None:
    """Parse a raw CSV row from Redfin into a Listing object."""
    try:
        price_raw = row.get("PRICE") or ""
        price_str = price_raw.replace("$", "").replace(",", "").strip()
        if not price_str:
            return None
        price = float(price_str)
    except (ValueError, TypeError):
        return None

    if price <= 0:
        return None

    def safe_int(val, default=0):
        try:
            return int(float(val)) if val else default
        except (ValueError, TypeError):
            return default

    def safe_float(val, default=0.0):
        try:
            return float(val) if val else default
        except (ValueError, TypeError):
            return default

    sqft = safe_int(row.get("SQUARE FEET"))
    hoa_raw = row.get("HOA/MONTH") or ""
    hoa_str = hoa_raw.replace("$", "").replace(",", "").strip()
    hoa = safe_float(hoa_str) if hoa_str and hoa_str != "—" else 0.0

    lat = safe_float(row.get("LATITUDE"))
    lng = safe_float(row.get("LONGITUDE"))

    listing = Listing(
        address=row.get("ADDRESS", "").strip(),
        city=row.get("CITY", city.split(",")[0]).strip(),
        state=row.get("STATE OR PROVINCE", "CA").strip(),
        zip_code=row.get("ZIP OR POSTAL CODE", "").strip(),
        price=price,
        beds=safe_int(row.get("BEDS")),
        baths=safe_float(row.get("BATHS")),
        sqft=sqft,
        price_per_sqft=round(price / sqft, 2) if sqft > 0 else 0,
        lot_size=row.get("LOT SIZE", "").strip(),
        year_built=safe_int(row.get("YEAR BUILT")),
        property_type=row.get("PROPERTY TYPE", "").strip(),
        hoa=hoa,
        listing_url=row.get("URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)", "").strip(),
        days_on_market=safe_int(row.get("DAYS ON MARKET")),
        status=row.get("STATUS", "").strip(),
        latitude=lat,
        longitude=lng,
    )

    return listing


def enrich_with_mortgage(listing: Listing) -> Listing:
    """Add mortgage calculations to a listing."""
    mortgage = calculate_mortgage(
        price=listing.price,
        hoa_monthly=listing.hoa,
    )
    listing.down_payment = mortgage.down_payment
    listing.monthly_mortgage = mortgage.monthly_principal_interest
    listing.monthly_total = mortgage.total_monthly_payment
    listing.total_interest = mortgage.total_interest_paid
    return listing


# ── Output ────────────────────────────────────────────────────────────────────


def save_to_csv(listings: list[Listing], filename: str):
    """Save listings to CSV."""
    if not listings:
        print("No listings to save.")
        return

    fieldnames = [
        "address", "city", "state", "zip_code", "price", "beds", "baths",
        "sqft", "price_per_sqft", "lot_size", "year_built", "property_type",
        "hoa", "days_on_market", "status", "listing_url",
        "latitude", "longitude",
        "down_payment", "monthly_mortgage", "monthly_total", "total_interest",
    ]

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for listing in listings:
            writer.writerow({k: getattr(listing, k) for k in fieldnames})

    print(f"\nSaved {len(listings)} listings to {filename}")


def save_to_json(listings: list[Listing], filename: str):
    """Save listings to JSON for the web app."""
    import os
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    # Filter out listings without geo data
    data = []
    for l in listings:
        d = asdict(l)
        if d["latitude"] != 0 and d["longitude"] != 0:
            data.append(d)

    with open(filename, "w") as f:
        json.dump(data, f)

    print(f"Saved {len(data)} geo-located listings to {filename}")


def print_summary(listings: list[Listing]):
    """Print a summary of the scraped listings."""
    if not listings:
        print("No listings found.")
        return

    prices = [l.price for l in listings]
    monthlies = [l.monthly_total for l in listings]

    print("\n" + "=" * 70)
    print("SOUTH BAY HOUSING SEARCH SUMMARY")
    print("=" * 70)
    print(f"Total listings found: {len(listings)}")
    print(f"Price range: ${min(prices):,.0f} — ${max(prices):,.0f}")
    print(f"Median price: ${sorted(prices)[len(prices)//2]:,.0f}")
    print(f"Monthly payment range: ${min(monthlies):,.0f} — ${max(monthlies):,.0f}")
    print(f"Median monthly payment: ${sorted(monthlies)[len(monthlies)//2]:,.0f}")
    print()

    # Breakdown by city
    cities = {}
    for l in listings:
        cities.setdefault(l.city, []).append(l.price)

    print(f"{'City':<20} {'Count':>6} {'Median Price':>14} {'Avg $/sqft':>12}")
    print("-" * 55)
    for city_name in sorted(cities):
        city_listings = [l for l in listings if l.city == city_name]
        city_prices = cities[city_name]
        median_p = sorted(city_prices)[len(city_prices) // 2]
        sqft_prices = [l.price_per_sqft for l in city_listings if l.price_per_sqft > 0]
        avg_sqft = sum(sqft_prices) / len(sqft_prices) if sqft_prices else 0
        print(f"{city_name:<20} {len(city_prices):>6} ${median_p:>12,.0f} ${avg_sqft:>10,.0f}")

    print()

    # Top 5 best value (lowest $/sqft with at least 2 beds)
    valued = [l for l in listings if l.price_per_sqft > 0 and l.beds >= 2]
    valued.sort(key=lambda l: l.price_per_sqft)

    print("TOP 10 BEST VALUE (lowest $/sqft, 2+ beds):")
    print("-" * 70)
    for l in valued[:10]:
        print(
            f"  ${l.price:>12,.0f}  {l.beds}bd/{l.baths}ba  {l.sqft:>5,}sqft  "
            f"${l.price_per_sqft:>6,.0f}/sqft  ${l.monthly_total:>7,.0f}/mo"
        )
        print(f"    {l.address}, {l.city}")
        if l.listing_url:
            print(f"    {l.listing_url}")
    print()

    # Affordability tiers
    print("MONTHLY PAYMENT TIERS (with 20% down, 6.5% rate):")
    print("-" * 50)
    tiers = [
        ("Under $4,000/mo", 0, 4000),
        ("$4,000–$6,000/mo", 4000, 6000),
        ("$6,000–$8,000/mo", 6000, 8000),
        ("$8,000–$10,000/mo", 8000, 10000),
        ("Over $10,000/mo", 10000, float("inf")),
    ]
    for label, lo, hi in tiers:
        count = sum(1 for l in listings if lo <= l.monthly_total < hi)
        print(f"  {label:<25} {count:>5} listings")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    print("South Bay Housing Scraper")
    print(f"Searching {len(SOUTH_BAY_CITIES)} cities...")
    print(f"Price range: ${DEFAULT_FILTERS['min_price']:,} — ${DEFAULT_FILTERS['max_price']:,}")
    print(f"Beds: {DEFAULT_FILTERS['min_beds']}+")
    print()

    all_listings: list[Listing] = []
    seen_addresses: set[str] = set()

    for city, region_id in SOUTH_BAY_CITIES.items():
        print(f"Searching {city}...", end=" ", flush=True)
        time.sleep(2)  # be polite to Redfin's servers

        raw_rows = fetch_redfin_listings(city, region_id, DEFAULT_FILTERS)
        count = 0

        for row in raw_rows:
            listing = parse_listing(row, city)
            if listing is None:
                continue

            # Deduplicate by address
            addr_key = listing.address.lower().strip()
            if addr_key in seen_addresses:
                continue
            seen_addresses.add(addr_key)

            enrich_with_mortgage(listing)
            all_listings.append(listing)
            count += 1

        print(f"found {count} listings")

    # Sort by price
    all_listings.sort(key=lambda l: l.price)

    # Output
    save_to_csv(all_listings, OUTPUT_CSV)
    save_to_json(all_listings, OUTPUT_JSON)
    print_summary(all_listings)

    print(f"CSV saved to: {OUTPUT_CSV}")
    print(f"JSON saved to: {OUTPUT_JSON}")
    print("Open the web app: cd web && python -m http.server 8000")


if __name__ == "__main__":
    main()
