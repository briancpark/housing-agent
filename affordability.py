"""
Personalized affordability analysis.
"""

import json

BASE_SALARY = 160_000
RSU = 40_000
TOTAL_COMP = BASE_SALARY + RSU

RATE = 0.065
TERM = 30
TAX_RATE = 0.012
INS_ANNUAL = 1800


def max_home_price(annual_income, ratio=0.28):
    """Back-calculate max home price from income using front-end ratio."""
    monthly_gross = annual_income / 12
    max_housing = monthly_gross * ratio
    r = RATE / 12
    n = TERM * 12
    pi_factor = 0.8 * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    tax_factor = TAX_RATE / 12
    price = (max_housing - INS_ANNUAL / 12) / (pi_factor + tax_factor)
    return price


def monthly_payment(price, hoa=0):
    loan = price * 0.80
    r = RATE / 12
    n = TERM * 12
    pi = loan * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return pi + price * TAX_RATE / 12 + INS_ANNUAL / 12 + hoa


def main():
    print("=" * 60)
    print("AFFORDABILITY ANALYSIS")
    print(f"$200K comp ($160K salary + $40K RSU)")
    print("=" * 60)

    print()
    print("WHAT LENDERS SEE:")
    print("-" * 50)
    print(f"  Base salary:           ${BASE_SALARY:>10,}/yr  (${BASE_SALARY // 12:>7,}/mo)")
    print(f"  RSU (may not count):   ${RSU:>10,}/yr  (${RSU // 12:>7,}/mo)")
    print(f"  Total comp:            ${TOTAL_COMP:>10,}/yr  (${TOTAL_COMP // 12:>7,}/mo)")

    print()
    print("KEY ISSUE WITH RSUs:")
    print("  Most lenders want 2+ years of RSU vesting history to count")
    print("  them as income. If you just started, they'll likely only")
    print("  use your $160K base salary for qualification.")

    print()
    print("MAX HOME PRICE (28% front-end ratio, 20% down, 6.5%):")
    print("-" * 50)

    conservative_max = max_home_price(BASE_SALARY, 0.28)
    rsu_max = max_home_price(TOTAL_COMP, 0.28)
    stretch_max = max_home_price(BASE_SALARY, 0.35)

    scenarios = [
        ("Conservative (base only, 28%)", conservative_max),
        ("With RSUs counted (28%)", rsu_max),
        ("Stretch (base only, 35%)", stretch_max),
    ]

    for label, price in scenarios:
        down = price * 0.20
        mo = monthly_payment(price)
        print(f"  {label}")
        print(f"    Max price: ${price:>10,.0f}   Down: ${down:>9,.0f}   Monthly: ${mo:>7,.0f}")

    # What's available from scraped data
    print()
    print("=" * 60)
    print("WHAT'S AVAILABLE (from scraped listings)")
    print("=" * 60)

    with open("web/data/listings.json") as f:
        listings = json.load(f)

    tiers = [
        (f"Conservative max (~${conservative_max / 1000:.0f}K)", 0, conservative_max),
        (f"With RSUs (~${rsu_max / 1000:.0f}K)", 0, rsu_max),
        (f"Stretch (~${stretch_max / 1000:.0f}K)", 0, stretch_max),
    ]

    for label, lo, hi in tiers:
        # Filter: townhouses near Apple Park (Sunnyvale/Santa Clara/Cupertino), 2+ beds
        matches = [
            l for l in listings
            if lo <= l["price"] <= hi and l["beds"] >= 2
        ]
        townhouses = [l for l in matches if "Townhouse" in l.get("property_type", "")]
        nearby = [
            l for l in matches
            if l["city"] in ("Sunnyvale", "Santa Clara", "Cupertino", "Mountain View", "San Jose", "Milpitas", "Campbell")
        ]

        if not matches:
            print(f"\n  {label}: 0 listings")
            continue

        prices = sorted([l["price"] for l in matches])
        print(f"\n  {label}:")
        print(f"    All types: {len(matches)} listings (median ${prices[len(prices) // 2]:,.0f})")
        print(f"    Townhouses only: {len(townhouses)}")
        print(f"    Near Apple Park (<30 min): {len(nearby)}")

        # Top picks — townhouses near Apple Park
        nearby_th = [l for l in townhouses if l["city"] in ("Sunnyvale", "Santa Clara", "Cupertino", "Mountain View", "San Jose", "Milpitas", "Campbell")]
        nearby_th.sort(key=lambda l: l.get("price_per_sqft", 99999))

        if nearby_th:
            print(f"    Best townhouse picks near Apple Park:")
            for l in nearby_th[:5]:
                hoa_str = f" +${l['hoa']:.0f} HOA" if l.get("hoa", 0) > 0 else ""
                print(f"      ${l['price']:>10,.0f}  {l['beds']}bd/{l['baths']}ba  {l['sqft']:,}sqft  ${l['monthly_total']:,.0f}/mo{hoa_str}")
                print(f"        {l['address']}, {l['city']} {l['zip_code']}")

    # Take-home reality check
    print()
    print("=" * 60)
    print("TAKE-HOME PAY REALITY CHECK")
    print("=" * 60)

    gross_monthly = BASE_SALARY / 12
    federal = gross_monthly * 0.22
    state = gross_monthly * 0.065
    fica = gross_monthly * 0.0765
    take_home = gross_monthly - federal - state - fica

    print(f"  Gross monthly (salary):    ${gross_monthly:>8,.0f}")
    print(f"  Est. federal tax (~22%):   -${federal:>7,.0f}")
    print(f"  Est. CA state tax (~6.5%): -${state:>7,.0f}")
    print(f"  FICA (7.65%):              -${fica:>7,.0f}")
    print(f"  Est. take-home:            ${take_home:>8,.0f}/mo")
    print(f"  RSU vests (~quarterly):    +${RSU / 12:>7,.0f}/mo avg (taxed at vest)")
    print()

    for tag, price in [("$590K", 590_000), ("$745K", 745_000), ("$900K", 900_000)]:
        mo = monthly_payment(price)
        pct = mo / take_home * 100
        left = take_home - mo
        print(f"  {tag} home: ${mo:>6,.0f}/mo = {pct:.0f}% of take-home, ${left:>6,.0f} left over")

    print()
    print("=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    print(f"""
  Your sweet spot is roughly $600K-$750K.

  At $700K (townhouse):
    Down payment (20%):  $140,000
    Monthly payment:     ~${monthly_payment(700_000):,.0f}
    Left over:           ~${take_home - monthly_payment(700_000):,.0f}/mo

  What to look for:
    - Modern townhouses in Milpitas, Santa Clara, or San Jose
      (all within 20-30 min of Apple Park)
    - 2bd/2ba is plenty living alone
    - Watch HOA fees — they add up ($300-600/mo typical)
    - Newer builds (2015+) have lower maintenance

  Down payment savings needed:
    - 20% of $700K = $140K (avoids PMI)
    - 10% of $700K = $70K (but adds ~$400/mo PMI)
    - Closing costs: ~$15K-25K on top

  RSU strategy:
    - Save RSU vests toward down payment
    - $40K/yr in RSUs = $140K in ~3.5 years (pre-tax)
    - Or buy sooner with 10% down, refinance when you hit 20% equity
""")


if __name__ == "__main__":
    main()
