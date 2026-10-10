# Mandalay CPCB AQI Prediction

Flask prediction application using 24 existing XGBoost Delta models, the original 198-feature engineering pipeline, and the existing Mandalay PostgreSQL dashboard database. No retraining, new database, synthetic observations or database writes.

The responsive page shows current CPCB AQI and six pollutants, +1/+6/+12/+24 hour summaries, a 24-hour chart, the full hourly table, CPCB colors and precautions, Mandalay local timestamps in 12-hour AM/PM format, and dashboard navigation. It preserves the original dark UI, light/dark toggle, Chart.js styling, clickable health popups and separate precautions page.

## Local setup

From this repository directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Configure `DATABASE_URL` in a local `.env`, following `.env.example`. Do not overwrite a configured `.env` or publish credentials. All model artifacts must remain in `models/XGB_Mandalay_CPCB_Delta24_2026/` (override with `MODEL_DIR` if necessary).

```bash
.venv/bin/python scripts/validate_models.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_database.py
.venv/bin/gunicorn wsgi:app --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120
```

Open [Mandalay Prediction](http://127.0.0.1:8000/prediction.html), [AQI Categories & Precautions](http://127.0.0.1:8000/precautions.html), or [API health](http://127.0.0.1:8000/api/health).

The website polls read-only APIs every five minutes and preserves its selected theme. Forecasts cache by observation timestamp and model-bank version, with stable actual generation times. Delayed observations and retained forecasts are prominently labeled stale; origins never shift to the browser clock. Missing/incompatible models, unusable features or unavailable numeric CPCB AQI return a clear error if no previous forecast can be retained.

## API

| Endpoint | Successful response | Unavailable |
| --- | --- | --- |
| GET `/api/health` | Database read succeeds and all 24 models are validated | HTTP 503 |
| GET `/api/latest` | Latest real raw readings and recalculated CPCB details; stale flag included | HTTP 503 |
| GET `/api/prediction` | Current CPCB, feature count, origin and 24 delta forecasts | HTTP 503 |
| GET `/api/prediction/status` | `ready` or explicitly `stale`, model count, feature count, origin, generation time and warnings | HTTP 503 with reason |
| GET `/api/forecast` | Compatibility alias for `/api/prediction`, with the same JSON contract | HTTP 503 |

The displayed forecast clips the current-plus-delta sum to 0–500, following training evaluation. The unbounded sum and clipping flag are also available in JSON. The API preserves raw CO in µg/m³; the original UI displays converted CO in mg/m³, matching model features. Other pollutants display µg/m³. The city is Mandalay, Myanmar; `Asia/Yangon` remains the correct internal IANA timezone.

## Verification and deployment

```bash
RUN_LIVE_DATABASE_TESTS=1 .venv/bin/python -m pytest tests/test_live_database.py -q
node scripts/test_frontend.cjs
```

Node.js is needed only for the isolated frontend tests, not for running or deploying Flask. Browser layout, Chart.js and modal interactions were also tested separately against the real local app.

- [Inference contract](docs/INFERENCE.md): exact feature formulas and provenance.
- [Database contract](docs/DATABASE.md): existing schema, endpoint inspection, read-only controls.
- [CPCB methodology](docs/CPCB_METHOD.md): shared dashboard calculations and limitations.
- [Validation report](docs/VALIDATION.md): completed checks and live observation snapshot.
- [Render deployment instructions](docs/DEPLOYMENT.md): exact commands, model packaging and environment variables.
- [Automatic updates](docs/AUTOMATIC_UPDATES.md): polling, cache behavior and exact existing-dashboard cron verification/setup.
- [Separate dashboard navigation](docs/DASHBOARD_LINKS.md): instructions without changing either dashboard.
- [Model validation](docs/model_validation.json): per-horizon checks and artifact SHA-256 hashes.

`training/` contains the supplied reference notebook. It is never imported or executed by the app, tests, build command or request handlers. The test fixtures contain real historical public dashboard observations and have no production fallback role.

No GitHub push or Render deployment has been performed. Review and approve the local original-style UI before following the publication instructions.
