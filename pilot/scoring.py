"""Explainable rider score (300-850) from repayment, work consistency and riding behaviour.

Weights are placeholders until pilot outcomes (defaults, claims) can be used to fit them.
"""

from datetime import date, timedelta

from . import loans, telemetry


def score(conn, rider_id: int, as_of: date, window_days: int = 28) -> dict:
    vehicle = conn.execute("SELECT device_id FROM vehicles WHERE rider_id = ?", (rider_id,)).fetchone()
    if vehicle is None:
        raise KeyError(rider_id)
    device_id = vehicle["device_id"]
    loan = conn.execute("SELECT account_ref FROM loans WHERE device_id = ?", (device_id,)).fetchone()

    # Repayment: share of the last N daily checkpoints on which the rider was not late.
    on_time_days = 0
    for k in range(window_days):
        if loan is None or loans.status(conn, loan["account_ref"], as_of - timedelta(days=k)).days_late == 0:
            on_time_days += 1
    repayment = on_time_days / window_days

    days = [telemetry.daily_summary(conn, device_id, (as_of - timedelta(days=k)).isoformat())
            for k in range(window_days)]
    active_days = sum(1 for d in days if d["riding_hours"] >= 1)
    consistency = min(1.0, active_days / (window_days * 6 / 7))   # six working days a week = full marks

    km = sum(d["km"] for d in days)
    events = sum(d["overspeed_events"] + d["harsh_brakes"] for d in days)
    per_100km = events / km * 100 if km else 0.0
    safety = max(0.0, 1 - per_100km / 10)                          # 10+ events per 100 km = zero

    components = {"repayment": round(repayment, 3), "consistency": round(consistency, 3), "safety": round(safety, 3)}
    blended = 0.55 * repayment + 0.25 * consistency + 0.20 * safety
    return {"rider_id": rider_id, "as_of": as_of.isoformat(), "score": round(300 + 550 * blended),
            "components": components, "km": round(km, 1), "active_days": active_days,
            "events_per_100km": round(per_100km, 2)}
