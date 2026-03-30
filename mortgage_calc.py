"""
Interactive Mortgage Calculator
Run standalone to explore different scenarios for a home purchase.
"""

import sys


def calculate_mortgage(
    price: float,
    down_payment_pct: float = 0.20,
    interest_rate: float = 0.065,
    loan_term_years: int = 30,
    property_tax_rate: float = 0.012,
    insurance_annual: float = 1800,
    hoa_monthly: float = 0,
):
    """Calculate and display full mortgage breakdown."""
    down_payment = price * down_payment_pct
    loan_amount = price - down_payment

    r = interest_rate / 12
    n = loan_term_years * 12

    if r > 0:
        monthly_pi = loan_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    else:
        monthly_pi = loan_amount / n

    monthly_tax = (price * property_tax_rate) / 12
    monthly_ins = insurance_annual / 12
    total_monthly = monthly_pi + monthly_tax + monthly_ins + hoa_monthly

    total_paid = monthly_pi * n
    total_interest = total_paid - loan_amount

    # What salary do you need? (28% front-end ratio rule)
    required_gross_monthly = total_monthly / 0.28
    required_annual_salary = required_gross_monthly * 12

    print()
    print("=" * 55)
    print("MORTGAGE BREAKDOWN")
    print("=" * 55)
    print(f"  Home Price:            ${price:>14,.2f}")
    print(f"  Down Payment ({down_payment_pct*100:.0f}%):    ${down_payment:>14,.2f}")
    print(f"  Loan Amount:           ${loan_amount:>14,.2f}")
    print(f"  Interest Rate:         {interest_rate*100:>13.2f}%")
    print(f"  Loan Term:             {loan_term_years:>10} years")
    print()
    print("MONTHLY PAYMENT BREAKDOWN:")
    print("-" * 40)
    print(f"  Principal & Interest:  ${monthly_pi:>10,.2f}")
    print(f"  Property Tax:          ${monthly_tax:>10,.2f}")
    print(f"  Home Insurance:        ${monthly_ins:>10,.2f}")
    if hoa_monthly > 0:
        print(f"  HOA:                   ${hoa_monthly:>10,.2f}")
    print(f"  ─────────────────────────────────────")
    print(f"  TOTAL MONTHLY:         ${total_monthly:>10,.2f}")
    print()
    print("OVER THE LIFE OF THE LOAN:")
    print("-" * 40)
    print(f"  Total Paid:            ${total_paid:>14,.2f}")
    print(f"  Total Interest:        ${total_interest:>14,.2f}")
    print(f"  Interest as % of Loan: {total_interest/loan_amount*100:>13.1f}%")
    print()
    print("AFFORDABILITY:")
    print("-" * 40)
    print(f"  Min. Gross Salary (28% rule): ${required_annual_salary:>10,.0f}/yr")
    print(f"  Min. Gross Monthly Income:    ${required_gross_monthly:>10,.0f}/mo")
    print()

    # Amortization schedule — first 5 years
    print("AMORTIZATION PREVIEW (first 5 years):")
    print(f"  {'Year':<6} {'Payment':>10} {'Principal':>10} {'Interest':>10} {'Balance':>14}")
    print("  " + "-" * 54)

    balance = loan_amount
    for year in range(1, min(6, loan_term_years + 1)):
        year_principal = 0
        year_interest = 0
        for _ in range(12):
            month_interest = balance * r
            month_principal = monthly_pi - month_interest
            balance -= month_principal
            year_principal += month_principal
            year_interest += month_interest
        print(
            f"  {year:<6} ${monthly_pi * 12:>9,.0f} "
            f"${year_principal:>9,.0f} ${year_interest:>9,.0f} "
            f"${max(balance, 0):>13,.0f}"
        )
    print()


def compare_scenarios(price: float):
    """Compare different down payment / rate scenarios."""
    print()
    print("=" * 70)
    print(f"SCENARIO COMPARISON for ${price:,.0f} home")
    print("=" * 70)

    scenarios = [
        ("5% down, 6.5%",   0.05, 0.065),
        ("10% down, 6.5%",  0.10, 0.065),
        ("20% down, 6.5%",  0.20, 0.065),
        ("20% down, 6.0%",  0.20, 0.060),
        ("20% down, 5.5%",  0.20, 0.055),
        ("20% down, 7.0%",  0.20, 0.070),
    ]

    print(f"  {'Scenario':<22} {'Down Pmt':>12} {'Monthly P&I':>12} {'Monthly Total':>14} {'Total Interest':>15}")
    print("  " + "-" * 78)

    for label, dp_pct, rate in scenarios:
        dp = price * dp_pct
        loan = price - dp
        r = rate / 12
        n = 360
        monthly_pi = loan * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
        monthly_tax = (price * 0.012) / 12
        monthly_ins = 1800 / 12
        total_monthly = monthly_pi + monthly_tax + monthly_ins
        total_interest = monthly_pi * n - loan

        # PMI for < 20% down (roughly 0.5-1% of loan/year)
        pmi = 0
        if dp_pct < 0.20:
            pmi = (loan * 0.007) / 12  # ~0.7% of loan annually
            total_monthly += pmi

        pmi_note = " +PMI" if dp_pct < 0.20 else ""
        print(
            f"  {label:<22} ${dp:>10,.0f} ${monthly_pi:>10,.0f} "
            f"${total_monthly:>12,.0f}{pmi_note:<5} ${total_interest:>13,.0f}"
        )
    print()
    if any(dp < 0.20 for _, dp, _ in scenarios):
        print("  * PMI (Private Mortgage Insurance) estimated at 0.7% of loan/year.")
        print("    PMI is required when down payment < 20%. It drops off once you have 20% equity.")
    print()


def interactive():
    """Interactive mode."""
    print("\nMORTGAGE CALCULATOR")
    print("Press Enter to use defaults shown in [brackets]\n")

    try:
        price_input = input("Home price [$1,200,000]: ").replace(",", "").replace("$", "").strip()
        price = float(price_input) if price_input else 1_200_000

        dp_input = input("Down payment % [20]: ").replace("%", "").strip()
        dp_pct = float(dp_input) / 100 if dp_input else 0.20

        rate_input = input("Interest rate % [6.5]: ").replace("%", "").strip()
        rate = float(rate_input) / 100 if rate_input else 0.065

        hoa_input = input("Monthly HOA [$0]: ").replace("$", "").replace(",", "").strip()
        hoa = float(hoa_input) if hoa_input else 0

    except (ValueError, EOFError):
        print("Invalid input. Using defaults.")
        price, dp_pct, rate, hoa = 1_200_000, 0.20, 0.065, 0

    calculate_mortgage(price, dp_pct, rate, hoa_monthly=hoa)
    compare_scenarios(price)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Quick mode: just pass a price
        price = float(sys.argv[1].replace(",", "").replace("$", ""))
        calculate_mortgage(price)
        compare_scenarios(price)
    else:
        interactive()
