"""Stdlib JSON API for the pilot.  Run: python3 -m pilot.server --db pilot.db --port 8000"""

import argparse
import json
import re
from dataclasses import asdict
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import db, loans, mpesa, scoring, telemetry


def make_handler(conn):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

        def do_POST(self):
            if self.path == "/mpesa/c2b/confirmation":
                mpesa.record_c2b(conn, self._body())
                # Daraja expects this exact acknowledgement shape.
                return self._send(200, {"ResultCode": 0, "ResultDesc": "Accepted"})
            if m := re.fullmatch(r"/devices/([\w-]+)/positions", self.path):
                return self._send(200, {"inserted": telemetry.ingest(conn, m[1], self._body()["points"])})
            if self.path == "/jobs/collections":
                as_of = date.fromisoformat(self._body().get("as_of", date.today().isoformat()))
                return self._send(200, {"actions": loans.run_collections(conn, as_of)})
            self._send(404, {"error": "not found"})

        def do_GET(self):
            try:
                if m := re.fullmatch(r"/loans/([\w-]+)", self.path):
                    return self._send(200, asdict(loans.status(conn, m[1].upper(), date.today())))
                if m := re.fullmatch(r"/riders/(\d+)/score", self.path):
                    return self._send(200, scoring.score(conn, int(m[1]), date.today()))
                if m := re.fullmatch(r"/devices/([\w-]+)/commands", self.path):
                    rows = conn.execute("SELECT * FROM commands WHERE device_id = ? AND status = 'PENDING'",
                                        (m[1],)).fetchall()
                    return self._send(200, [dict(r) for r in rows])
            except KeyError:
                return self._send(404, {"error": "not found"})
            self._send(404, {"error": "not found"})

    return Handler


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="pilot.db")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), make_handler(db.connect(args.db)))
    print(f"listening on :{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
