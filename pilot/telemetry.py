"""Tracker position ingestion and daily riding summaries."""

import math
from datetime import datetime

OVERSPEED_KMH = 60.0
HARSH_BRAKE_KMH_PER_S = 7.0   # ~0.2 g


def ingest(conn, device_id: str, points: list[dict]) -> int:
    rows = [(device_id, p["ts"], p["lat"], p["lon"], p["speed_kmh"], int(bool(p["ignition"]))) for p in points]
    cur = conn.executemany("INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return cur.rowcount


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def daily_summary(conn, device_id: str, day: str) -> dict:
    pts = conn.execute(
        "SELECT * FROM positions WHERE device_id = ? AND substr(ts, 1, 10) = ? ORDER BY ts",
        (device_id, day),
    ).fetchall()
    km = hours = 0.0
    overspeed = harsh = 0
    for prev, cur in zip(pts, pts[1:]):
        dt = (datetime.fromisoformat(cur["ts"]) - datetime.fromisoformat(prev["ts"])).total_seconds()
        if dt <= 0 or dt > 600:   # gap in reporting: don't invent a trip across it
            continue
        if prev["ignition"] and cur["ignition"]:
            km += haversine_km(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
            if cur["speed_kmh"] > 3:
                hours += dt / 3600
        if cur["speed_kmh"] > OVERSPEED_KMH >= prev["speed_kmh"]:
            overspeed += 1
        if (prev["speed_kmh"] - cur["speed_kmh"]) / dt >= HARSH_BRAKE_KMH_PER_S:
            harsh += 1
    return {"device_id": device_id, "day": day, "km": round(km, 2), "riding_hours": round(hours, 2),
            "overspeed_events": overspeed, "harsh_brakes": harsh}
