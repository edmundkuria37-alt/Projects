"""Loan status and the collections policy: remind, warn, then immobilize on the next stop."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class LoanStatus:
    account_ref: str
    due_to_date: float
    paid: float
    arrears: float
    days_late: int        # days since the oldest installment that is not fully covered fell due
    balance: float
    cleared: bool


def status(conn, account_ref: str, as_of: date) -> LoanStatus:
    loan = conn.execute("SELECT * FROM loans WHERE account_ref = ?", (account_ref,)).fetchone()
    if loan is None:
        raise KeyError(account_ref)
    start = date.fromisoformat(loan["start_date"])
    cutoff = datetime.combine(as_of, datetime.max.time()).isoformat()
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE account_ref = ? AND paid_at <= ?",
        (account_ref, cutoff),
    ).fetchone()[0]

    total = loan["weekly_installment"] * loan["weeks"]
    due_dates = [start + timedelta(weeks=k) for k in range(1, loan["weeks"] + 1)]
    elapsed = [d for d in due_dates if d <= as_of]
    due = loan["weekly_installment"] * len(elapsed)

    # Payments cover installments oldest-first; the first uncovered one sets days_late.
    covered = int(paid // loan["weekly_installment"]) if loan["weekly_installment"] else len(elapsed)
    days_late = (as_of - elapsed[covered]).days if covered < len(elapsed) else 0

    return LoanStatus(account_ref, due, paid, max(0.0, due - paid), days_late,
                      max(0.0, total - paid), paid >= total)


def _remind(conn, msisdn: str, body: str, key: str, now: str) -> None:
    conn.execute("INSERT OR IGNORE INTO messages (msisdn, body, created_at, dedupe_key) VALUES (?, ?, ?, ?)",
                 (msisdn, body, now, key))


def _last_command(conn, device_id: str):
    return conn.execute("SELECT kind FROM commands WHERE device_id = ? ORDER BY id DESC LIMIT 1",
                        (device_id,)).fetchone()


def run_collections(conn, as_of: date) -> list[dict]:
    """Daily job. Never cuts a moving engine: the device is told to immobilize at its next ignition-off."""
    now = datetime.combine(as_of, datetime.min.time()).isoformat()
    actions = []
    rows = conn.execute("""
        SELECT l.account_ref, l.grace_days, v.device_id, r.msisdn
        FROM loans l JOIN vehicles v USING (device_id) JOIN riders r ON r.id = v.rider_id
    """).fetchall()
    for row in rows:
        s = status(conn, row["account_ref"], as_of)
        last = _last_command(conn, row["device_id"])
        immobilized = last is not None and last["kind"] == "IMMOBILIZE_ON_STOP"

        if s.days_late == 0 or s.cleared:
            if immobilized:
                conn.execute("INSERT INTO commands (device_id, kind, reason, created_at) VALUES (?, 'RELEASE', ?, ?)",
                             (row["device_id"], f"arrears cleared on {s.account_ref}", now))
                actions.append({"account_ref": s.account_ref, "action": "RELEASE"})
            continue

        if s.days_late > row["grace_days"]:
            if not immobilized:
                conn.execute(
                    "INSERT INTO commands (device_id, kind, reason, created_at) VALUES (?, 'IMMOBILIZE_ON_STOP', ?, ?)",
                    (row["device_id"], f"{s.days_late} days late, arrears KES {s.arrears:,.0f}", now))
                _remind(conn, row["msisdn"],
                        f"Account {s.account_ref}: KES {s.arrears:,.0f} overdue. The bike will not restart after "
                        f"you next switch off. Pay to paybill, account {s.account_ref}, to unlock.",
                        f"{s.account_ref}:immobilize:{as_of}", now)
                actions.append({"account_ref": s.account_ref, "action": "IMMOBILIZE_ON_STOP"})
        else:
            stage = "warning" if s.days_late == row["grace_days"] else "reminder"
            _remind(conn, row["msisdn"],
                    f"Account {s.account_ref}: KES {s.arrears:,.0f} is {s.days_late} day(s) late. "
                    f"Lock happens after {row['grace_days']} days.",
                    f"{s.account_ref}:{stage}:{as_of}", now)
            actions.append({"account_ref": s.account_ref, "action": stage.upper()})
    conn.commit()
    return actions
