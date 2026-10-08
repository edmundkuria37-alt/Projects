import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS riders (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    msisdn      TEXT NOT NULL UNIQUE,          -- 2547XXXXXXXX
    consent_at  TEXT                           -- Data Protection Act consent timestamp; no tracking without it
);
CREATE TABLE IF NOT EXISTS vehicles (
    device_id   TEXT PRIMARY KEY,              -- tracker IMEI
    plate       TEXT NOT NULL,
    rider_id    INTEGER NOT NULL REFERENCES riders(id),
    lender      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS loans (
    account_ref         TEXT PRIMARY KEY,      -- M-Pesa paybill account number the rider types
    device_id           TEXT NOT NULL REFERENCES vehicles(device_id),
    principal           REAL NOT NULL,
    weekly_installment  REAL NOT NULL,
    weeks               INTEGER NOT NULL,
    start_date          TEXT NOT NULL,         -- ISO date; first installment due start_date + 7 days
    grace_days          INTEGER NOT NULL DEFAULT 3
);
CREATE TABLE IF NOT EXISTS payments (
    receipt     TEXT PRIMARY KEY,              -- M-Pesa TransID; makes callbacks idempotent
    account_ref TEXT NOT NULL,
    amount      REAL NOT NULL,
    paid_at     TEXT NOT NULL,
    msisdn      TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    device_id   TEXT NOT NULL,
    ts          TEXT NOT NULL,
    lat         REAL NOT NULL,
    lon         REAL NOT NULL,
    speed_kmh   REAL NOT NULL,
    ignition    INTEGER NOT NULL,
    PRIMARY KEY (device_id, ts)
);
CREATE TABLE IF NOT EXISTS commands (
    id          INTEGER PRIMARY KEY,
    device_id   TEXT NOT NULL,
    kind        TEXT NOT NULL,                 -- IMMOBILIZE_ON_STOP | RELEASE
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING'
);
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    msisdn      TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL UNIQUE           -- one reminder per loan per stage per day
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
