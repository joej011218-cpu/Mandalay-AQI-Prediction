# Final local validation — 2026-10-10

No GitHub push or Render deployment was performed. The user must preview and approve the UI first. Neither existing dashboard repository or database was modified.

## Original UI restored

The supplied `reference_ui/prediction.html` and `reference_ui/precautions.html` match the original Mac files. Those files are preserved. Their original CSS was extracted directly to static assets; a regression test verifies it is preserved. The original HTML structure, dark colors, panels, spacing, fonts, centered title/clock/navigation, four cards, table, modal guidance and precautions cards were retained.

Only location/time formatting, Mandalay API adapters, navigation, freshness warnings, safe unavailable values, accessible category triggers and chart-update reuse were changed. Chart.js **4.5.1**, the original UI's version, is vendored locally. No runtime CDN or third-party data request is necessary. The public Vadodara navigation goes to `https://aiot-public-dashboard-2.onrender.com/`.

The live clock, observations, forecast origin, all forecast rows, chart tooltips, modal metadata and check/generation times use uppercase AM/PM. Internally timestamps remain aware ISO 8601 and `Asia/Yangon`. The monitored city is **Mandalay, Myanmar**.

Browser checks on the real locally running Gunicorn app verified:

- Current CPCB AQI and six genuine pollutants, including CO **0.281 mg/m³** converted from **281 µg/m³**.
- Correct +1/+6/+12/+24 cards, all 24 hourly table rows, and actual Chart.js rendering.
- Current category, forecast-card and table-category modals open and close; modal times use AM/PM.
- Dark mode by default, working light/dark toggles and shared theme persistence across Prediction and Precautions.
- Original six precautions cards, their colors, navigation and original guidance.
- No console warnings/errors.
- No document overflow at **390px mobile**, **768px tablet**, or **1280px desktop**. The original hourly table can scroll horizontally within its wrapper on small screens.
- Prominent orange stale-data banner near the navigation, actual observation/generation times, and retained old origins.

Screenshots are saved under `docs/screenshots/`. Isolated frontend tests verify the five-minute timer, focus/visibility coalescing, no duplicate Chart.js construction, chart tooltip formatting, theme preservation, popups, null values and failure retention. They do not replace browser rendering checks.

## Model and feature validation

All 24 trusted XGBRegressor artifacts loaded successfully, horizons +1 through +24. Every config identifies Indian CPCB AQI, `cpcb-2014-rolling-v1`, CO mg/m³, other pollutants µg/m³, Asia/Yangon, and 198 ordered features. Booster feature names/count/order and objective match the saved manifest. Original model SHA-256 hashes remain unchanged.

The original supplied training notebook's functions exactly match the Downloads training script by AST. The inference vector matches an independently generated original-training feature vector exactly after float32 conversion on real history. All 24 models produce finite horizon-specific deltas; displayed bounds match the original training evaluation. Training was never run. Model-bank version hashes all original model/config/feature artifacts for cache keys.

XGBoost 3.2.0 emitted one older-serialization warning. All models pass actual inference in the pinned environment. Original training library versions are not recorded, so saved training metrics are not treated as newly measured accuracy or confidence intervals.

## Existing PostgreSQL and real APIs

The secure local `.env` was loaded without printing credentials. Existing schema columns were inspected and `SHOW transaction_read_only` returned **on**. The inference query retrieved **192 canonical hourly observations**. No DDL, record updates/deletes, administrative refresh or new database was used.

All four required APIs and the `/api/forecast` alias work locally without viewer authentication. Live database integration, full feature generation and all 24 real-model predictions passed. `/api/health` reports database connectivity and loaded models; forecast status independently reports freshness.

Final observation origin remained **10 Oct 2026, 1:00 PM Asia/Yangon**, CPCB AQI **68**. At final verification it was over three hours old; `/api/prediction` and `/api/prediction/status` correctly reported **stale**, rather than claiming current fresh data.

| Horizon | Predicted CPCB AQI from that real origin |
| --- | --- |
| +1h | 78.09 |
| +6h | 74.69 |
| +12h | 47.99 |
| +24h | 73.59 |

Full real inference, actual generation time, warnings, origin and PostgreSQL schema types are recorded in `live_validation.json`. No credentials are included. Values are a tested delayed-data snapshot, not a claim that the same values remain current.

## Tests

- `.venv/bin/python -m pytest -q`: **69 passed, 1 skipped**. The skip is the opt-in live database test.
- `RUN_LIVE_DATABASE_TESTS=1 .venv/bin/python -m pytest tests/test_live_database.py -q`: **1 passed**, read-only against the existing real database.
- `node scripts/test_frontend.cjs`: **passed** all isolated frontend checks listed above.
- Python compilation, JS syntax checks, dependency `pip check`, artifact hash comparison and Git whitespace check passed.
- Tests cover invalid CPCB/model horizon/feature metadata, missing history, exact units/features, timezone alignment, Severe-band unavailability, read-only connection settings, API errors, stale cold-start labeling, outage retention, new valid/invalid origins, cache model version and concurrent single-flight inference.

## Automatic update status and remaining blockers

Five-minute browser polling and origin/model-version prediction caching are implemented and tested. The existing dashboard's repository declares hourly `mandalay-aqi-hourly` with `flask --app wsgi refresh-data`. Its actual Render scheduled run logs and active deployment were not accessible; operational hourly collection remains **unverified**. The current delayed observation reinforces the need to inspect that job, but does not establish the cause of the delay. Exact verification and setup instructions are in `AUTOMATIC_UPDATES.md`.

Render deployment, production network access and public HTTPS behavior remain untested until the user approves publication and deployment. The existing dashboards are preserved; `DASHBOARD_LINKS.md` supplies separate navigation instructions. The model bundle fits GitHub's current file limit. No runtime model download or retraining is needed. The deployment uses one worker, four threads, one loaded model bank and a bounded origin cache; each regressor uses one prediction thread. A local worker RSS sample was 10,816 KiB, which is a single macOS resident-memory sample, not a Linux peak-memory guarantee. Verify Render's memory metrics after deployment.

## Files modified or added for this final specification

Modified: `app.py`, `prediction/models.py`, `prediction/service.py`, `templates/prediction.html`, `static/app.js`, `static/style.css`, `.env.example`, `render.yaml`, `README.md`, `tests/test_pipeline.py`, `docs/INFERENCE.md`, `docs/DATABASE.md`, `docs/DEPLOYMENT.md`, `docs/VALIDATION.md`, `docs/provenance.json`, `docs/model_validation.json`, `docs/live_validation.json`.

Added: `templates/precautions.html`, `static/clock.js`, `static/precautions.css`, `static/precautions.js`, `static/vendor/chart.umd.min.js`, `scripts/test_frontend.cjs`, `tests/fixtures/mandalay_previous_origin.json`, `docs/AUTOMATIC_UPDATES.md`, `docs/DASHBOARD_LINKS.md`, and `docs/screenshots/` evidence.

Existing backend modules `prediction/database.py`, `prediction/features.py`, `prediction/cpcb.py`, `prediction/training_features.py`, `wsgi.py`, original model artifacts and training/reference files were preserved. No changes were made to `.env`. The ignored `.venv/` contains installed dependencies.

## Local preview URLs

- Prediction: http://127.0.0.1:8000/prediction.html (also `/`).
- Precautions: http://127.0.0.1:8000/precautions.html.
- API health: http://127.0.0.1:8000/api/health.

GitHub publication commands and exact Render settings are in `DEPLOYMENT.md`; do not run them until the user approves the preview.
