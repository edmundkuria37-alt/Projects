"""Cohort-based unit-economics model for the boda boda telematics business.

Run:  python3 model/unit_economics.py            # base case
      python3 model/unit_economics.py --sweep    # sensitivity on the assumptions that matter most

Every number below is an assumption to be replaced with pilot data. The point of
the model is to show which assumptions the $1M/yr target actually depends on.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

KES_PER_USD = 129.0


@dataclass(frozen=True)
class Assumptions:
    months: int = 36
    # Install ramp: new tracked vehicles per month in year 1, 2, 3.
    installs_per_month: tuple[int, int, int] = (150, 600, 1000)

    # Revenue
    saas_fee: float = 650.0            # KES / vehicle / month, paid by lender while the loan runs
    device_price: float = 5_500.0      # KES charged per installed unit (usually bundled into the loan)
    insurance_attach: float = 0.25     # share of active vehicles holding a policy sold through us
    premium_per_month: float = 500.0   # KES average micro-premium per insured vehicle
    commission: float = 0.125          # agent commission on premiums

    # Lifetime
    loan_term_months: int = 18         # lender stops paying when the loan is cleared
    early_exit_monthly: float = 0.015  # repossession, write-off, device destroyed
    post_loan_retention: float = 0.20  # share who keep a rider-paid plan after payoff
    post_loan_fee: float = 250.0       # KES / month, rider-paid (theft recovery + score)

    # Costs
    device_cogs: float = 4_000.0       # tracker + relay + harness, landed
    install_cost: float = 600.0        # technician time + transport
    connectivity: float = 120.0        # M2M SIM data per device per month
    support_per_vehicle: float = 60.0  # field support, re-installs, tamper call-outs


def simulate(a: Assumptions) -> list[dict]:
    """Returns one row per month with active vehicles, revenue lines and gross margin."""
    cohorts: list[int] = []  # cohorts[i] = installs in month i
    rows = []
    for m in range(a.months):
        cohorts.append(a.installs_per_month[min(m // 12, 2)])

        on_loan = 0.0
        post_loan = 0.0
        for start, n in enumerate(cohorts):
            age = m - start
            survive = n * (1 - a.early_exit_monthly) ** age
            if age < a.loan_term_months:
                on_loan += survive
            else:
                post_loan += survive * a.post_loan_retention

        active = on_loan + post_loan
        new = cohorts[-1]
        rev_saas = on_loan * a.saas_fee + post_loan * a.post_loan_fee
        rev_device = new * a.device_price
        rev_ins = active * a.insurance_attach * a.premium_per_month * a.commission
        cost = new * (a.device_cogs + a.install_cost) + active * (a.connectivity + a.support_per_vehicle)
        rows.append({
            "month": m + 1,
            "new": new,
            "on_loan": on_loan,
            "post_loan": post_loan,
            "active": active,
            "revenue": rev_saas + rev_device + rev_ins,
            "rev_saas": rev_saas,
            "rev_device": rev_device,
            "rev_ins": rev_ins,
            "gross_profit": rev_saas + rev_device + rev_ins - cost,
        })
    return rows


def yearly(rows: list[dict]) -> list[dict]:
    out = []
    for y in range(len(rows) // 12):
        chunk = rows[y * 12:(y + 1) * 12]
        out.append({
            "year": y + 1,
            "installs": sum(r["new"] for r in chunk),
            "active_end": chunk[-1]["active"],
            "revenue": sum(r["revenue"] for r in chunk),
            "rev_saas": sum(r["rev_saas"] for r in chunk),
            "rev_device": sum(r["rev_device"] for r in chunk),
            "rev_ins": sum(r["rev_ins"] for r in chunk),
            "gross_profit": sum(r["gross_profit"] for r in chunk),
        })
    return out


def steady_state_installs_per_month(target_active: float, a: Assumptions) -> float:
    """Monthly installs needed to hold `target_active` vehicles once cohorts have matured."""
    per_install = sum((1 - a.early_exit_monthly) ** k for k in range(a.loan_term_months))
    per_install += a.post_loan_retention * sum(
        (1 - a.early_exit_monthly) ** k for k in range(a.loan_term_months, 240))
    return target_active / per_install


def _m(kes: float) -> str:
    return f"KES {kes / 1e6:6.1f}M (${kes / KES_PER_USD / 1e3:5.0f}k)"


def report(a: Assumptions) -> None:
    print(f"{'Year':<5}{'Installs':>9}{'Active(end)':>13}  {'Revenue':<24}{'Gross profit':<24}")
    for y in yearly(simulate(a)):
        print(f"{y['year']:<5}{y['installs']:>9,}{y['active_end']:>13,.0f}  {_m(y['revenue']):<24}{_m(y['gross_profit']):<24}")
    y3 = yearly(simulate(a))[-1]
    print(f"\nYear-3 mix: SaaS {y3['rev_saas'] / y3['revenue']:.0%}, devices {y3['rev_device'] / y3['revenue']:.0%}, "
          f"insurance {y3['rev_ins'] / y3['revenue']:.0%}")
    print(f"Installs/month needed to hold 15,000 active vehicles: {steady_state_installs_per_month(15_000, a):,.0f}")


def sweep(a: Assumptions) -> None:
    cases = {
        "base": a,
        "loan term 12m": replace(a, loan_term_months=12),
        "loan term 24m": replace(a, loan_term_months=24),
        "SaaS fee 400": replace(a, saas_fee=400),
        "post-loan retention 0%": replace(a, post_loan_retention=0.0),
        "post-loan retention 50%": replace(a, post_loan_retention=0.5),
        "insurance attach 50%": replace(a, insurance_attach=0.5),
        "early exit 3%/mo": replace(a, early_exit_monthly=0.03),
        "device sold at cost": replace(a, device_price=a.device_cogs + a.install_cost),
    }
    print(f"{'Scenario':<26}{'Y3 revenue':<24}{'Y3 gross profit':<24}{'Installs/mo for 15k':>20}")
    for name, c in cases.items():
        y3 = yearly(simulate(c))[-1]
        print(f"{name:<26}{_m(y3['revenue']):<24}{_m(y3['gross_profit']):<24}"
              f"{steady_state_installs_per_month(15_000, c):>20,.0f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sweep", action="store_true")
    args = p.parse_args()
    (sweep if args.sweep else report)(Assumptions())
