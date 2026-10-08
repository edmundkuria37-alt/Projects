"""Handles Safaricom Daraja C2B confirmation callbacks for the lender's paybill."""

from datetime import datetime


def parse_trans_time(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d%H%M%S").isoformat()


def record_c2b(conn, payload: dict) -> dict:
    """Stores one C2B confirmation. Duplicate callbacks for the same TransID are ignored.

    Returns {"stored": bool, "matched": bool}; unmatched payments are kept for manual reconciliation.
    """
    account_ref = payload["BillRefNumber"].strip().upper()
    cur = conn.execute(
        "INSERT OR IGNORE INTO payments (receipt, account_ref, amount, paid_at, msisdn) VALUES (?, ?, ?, ?, ?)",
        (payload["TransID"], account_ref, float(payload["TransAmount"]),
         parse_trans_time(payload["TransTime"]), payload.get("MSISDN")),
    )
    conn.commit()
    matched = conn.execute("SELECT 1 FROM loans WHERE account_ref = ?", (account_ref,)).fetchone() is not None
    return {"stored": cur.rowcount == 1, "matched": matched}
