# Pay-As-You-Ride Telematics for Boda Boda Financing and Insurance

A stress-tested version of the original idea. The numbers come from
`model/unit_economics.py`. They are assumptions until the pilot replaces them.

## The idea in one paragraph

A low-cost GPS tracker with an ignition-cut relay (KES 3,500–5,000 a unit), sold to
SACCOs, dealer finance arms and asset financiers. Lenders pay a monthly SaaS fee
for location, remote immobilization and M-Pesa repayment tracking. Riders get a
credit profile built from repayment and riding data, which can unlock cheaper loans,
spare-part credit and usage-based insurance sold through a licensed underwriter.

## What the model says

Base case: 150 installs a month in year 1, 600 in year 2, 1,000 in year 3; KES 650 a
month SaaS fee while the loan runs; 18-month loans; 20% of riders keep a KES 250
rider-paid plan after payoff.

| Year | Installs | Active vehicles (end) | Revenue | Gross profit |
|---|---|---|---|---|
| 1 | 1,800 | 1,659 | KES 17.3M ($134k) | KES 7.0M ($54k) |
| 2 | 7,200 | 7,490 | KES 79.7M ($618k) | KES 35.7M ($277k) |
| 3 | 12,000 | 14,710 | KES 159.4M ($1.24M) | KES 78.5M ($608k) |

The KES 130M ($1M) run rate is reachable in year 3, but the model differs from the
original pitch in four ways:

1. **Installs, not active vehicles, are the real target.** The lender stops paying
   when the loan is cleared, so every vehicle churns after 12 to 24 months. Holding
   15,000 active vehicles takes **about 580 to 950 new installs a month**
   (7,000–11,000 a year), not "a few thousand". The deciding factor is how many riders
   keep a paid plan after payoff. Plan sales capacity for that from day one.
2. **Device revenue is about 40% of year-3 revenue.** That is lumpy and depends on
   lender volume. Recurring SaaS is about 57%.
3. **Insurance commission is about 1% of revenue.** At a 25% attach rate, a KES 500
   monthly premium and 12.5% commission, insurance doesn't move the top line. Its
   value is strategic: it is the hook for rider adoption and data partnerships. Don't
   build the plan around it.
4. **Price matters most.** Dropping the SaaS fee to KES 400 cuts year-3 gross profit
   by 44%. Tracker firms already sell tracking-only plans more cheaply, so the
   KES 650 fee has to be justified by collections results (lower default and
   repossession costs), not by GPS.

Run `python3 model/unit_economics.py --sweep` for the full sensitivity table.

## Who you're competing with

- **Large PAYG asset financiers** (Watu, M-KOPA, Mogo and similar) already put
  trackers and immobilizers on bikes they finance, in house. They are a reference
  for the model, not customers.
- **The addressable gap** is the long tail: SACCOs, dealer credit desks, chamas and
  smaller asset financiers who don't have their own telematics stack or collections
  tooling.
- **Generic tracker installers** compete on price for hardware. Win on the
  lender workflow instead: M-Pesa reconciliation, automated reminders, policy-driven
  immobilization and portfolio reporting.

## Risks the original plan understates

| Risk | Why it matters | Mitigation |
|---|---|---|
| **Cutting a moving engine** | Immobilizing a bike in traffic can kill someone and creates direct liability. | Only arm the cut at the next ignition-off (the pilot backend does this) and never cut above walking speed. Put this in firmware and in the lender contract. |
| **Data protection** | The Kenya Data Protection Act 2019 requires a lawful basis, registration with the ODPC, and explicit, informed consent for location data. Selling "anonymized mobility data" later needs real aggregation, not just removing names. | Record consent before activation (the `consent_at` field). Register as a data processor. Only sell aggregated data, such as corridor-level speeds and heatmaps with minimum group sizes. |
| **Insurance licensing** | Selling policies requires an IRA-licensed intermediary. | Operate as an agent of a licensed underwriter, or partner with a licensed broker. Look into IRA's regulatory sandbox for usage-based pricing. |
| **Rider churn after loan payoff** | This is the largest driver of how many installs you need. | Give the rider-paid plan its own value: theft recovery, a portable credit score, and a path to the next loan. |
| **Device tampering and theft** | A relay can be bypassed or a tracker unplugged. | Use tamper and power-cut alerts, a hidden backup battery, and covert install points. Measure tamper rate as a pilot KPI. |
| **Lender concentration** | Eight to twelve clients means one lost SACCO can cost 10% or more of revenue. | Sign multi-year contracts with volume tiers, and pursue exclusive dealer-network deals early. |
| **Connectivity cost** | M2M data and SMS cost about KES 100–200 per device per month. | Tune the reporting interval: 30 seconds while moving and hourly heartbeats while parked. |

## 90-day pilot, with success criteria set in advance

**Partner:** one SACCO or dealer finance arm, 100 bikes. Use a comparable untracked
group from the same lender as the control.

| Weeks | Deliverable |
|---|---|
| 1–3 | Choose tracker hardware (two vendors, 10 units each, bench and road tests). Sign the pilot agreement, data processing agreement and rider consent form. Set up the Daraja C2B paybill. |
| 3–5 | Install on 100 bikes. Run the pilot backend (`pilot/`) with real callbacks. Send SMS reminders. |
| 5–12 | Live collections policy (remind, warn, then lock at next stop). Weekly portfolio report to the lender. |
| 10–12 | Fit the first rider score to observed lateness. Take the data pack to two insurers. |

Decide whether to continue using these KPIs:

- **PAR-7** (share of the portfolio more than 7 days late), pilot vs control. Target: at
  least 30% relative reduction.
- **Repossessions and write-offs** per 100 bikes, pilot vs control.
- **Recovery rate** for stolen bikes.
- **Tamper or offline rate**: under 5% of devices offline for more than 48 hours.
- **Rider net promoter score and complaints**: proof that adoption by riders is real.
- **Willingness to pay**: the lender signs a paid rollout at at least KES 500 a month for at least 500 bikes.

If PAR-7 doesn't move, the KES 650 price can't be defended. Re-price, or narrow the
product to theft recovery.

## Software in this repo

`pilot/` is a dependency-free Python backend covering what the pilot needs:

- `mpesa.py`: idempotent Daraja C2B confirmation handling (matches on paybill account number).
- `loans.py`: weekly installment schedule, arrears, days late, and the collections
  job (reminder, then warning, then lock at next ignition-off, then release on payment).
- `telemetry.py`: position ingest, daily distance, riding hours, overspeed and harsh braking.
- `scoring.py`: explainable 300–850 rider score (repayment 55%, consistency 25%,
  safety 20%). The weights are placeholders until pilot outcomes are available.
- `server.py`: JSON API, including the device command poll endpoint the tracker firmware uses.

Not built yet: the lender dashboard UI, the SMS gateway integration (messages are
queued in the `messages` table), STK Push, authentication, and tracker protocol
adapters (most cheap trackers speak GT06 or similar over TCP, so a small gateway
converts those to the `/devices/{id}/positions` JSON).
