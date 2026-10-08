# Boda Boda Pay-As-You-Ride Telematics

GPS and immobilizer tracking, M-Pesa repayment tracking and rider credit scoring for
boda boda and tuk-tuk financing in Kenya.

- [`docs/business-plan.md`](docs/business-plan.md): the stress-tested plan, risks and 90-day pilot design
- `model/unit_economics.py`: cohort revenue model (`python3 model/unit_economics.py --sweep`)
- `pilot/`: stdlib-only pilot backend (`python3 -m pilot.server --db pilot.db`)
- `tests/`: `python3 -m unittest`

## API (pilot)

| Method | Path | Purpose |
|---|---|---|
| POST | `/mpesa/c2b/confirmation` | Daraja C2B confirmation callback |
| POST | `/devices/{imei}/positions` | `{"points": [{ts, lat, lon, speed_kmh, ignition}]}` |
| GET | `/devices/{imei}/commands` | Pending `IMMOBILIZE_ON_STOP` / `RELEASE` commands for the tracker |
| POST | `/jobs/collections` | Run the daily collections policy (`{"as_of": "YYYY-MM-DD"}`) |
| GET | `/loans/{account_ref}` | Arrears, days late, balance |
| GET | `/riders/{id}/score` | Rider score with component breakdown |
