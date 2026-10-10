# Existing Mandalay database integration

Dashboard source inspected at commit `8480f6d263b54ac36731dbfd595e2909a95f4fed` from https://github.com/joej011218-cpu/Mandalay-AQI-Dashboard.

The dashboard uses these PostgreSQL tables:

| Table | Columns used/relevant |
| --- | --- |
| `mandalay_readings` | `timestamp` timestamptz PK; float `pm2_5`, `pm10`, `carbon_monoxide`, `nitrogen_dioxide`, `sulphur_dioxide`, `ozone`; `source`; raw `us_aqi` retained by the dashboard but not queried by inference |
| `mandalay_cpcb_aqi` | timestamp PK/FK; integer nullable `cpcb_aqi`; `status`; `calculation_version`; `calculated_at`; JSONB `details` |
| `mandalay_source_observations` | timestamp + source_id PK; JSONB original_values/provenance; retained for audit, not needed by prediction |

`prediction/database.py` performs one SELECT joining readings to CPCB results, using the latest nonfuture canonical row as its origin. The canonical filter is `mod(extract(epoch FROM timestamp),3600)=1800`, corresponding to Yangon whole hours. It queries a 192-slot interval anchored to that origin. Raw concentrations all use µg/m³. Older UTC-aligned rows are excluded.

Both connection defaults and transaction settings enforce read-only operation. Connections have an 8-second connection timeout and a 10-second SQL statement timeout. No SQL schema creation, migrations, INSERT, UPDATE, DELETE, refresh or recalculation writes exist in this application. Connections close after each query; observations cache for 60 seconds. If a read fails after successful data were cached, retain that snapshot with an explicit source-outage warning and report the failure through health. Forecast timestamps remain anchored to observations, not request time. Prediction results cache by origin and model-bank version; repeated requests preserve the actual generation time. Database exception details and credentials are withheld from API responses.

The dashboard provides GET `/api/health`, `/api/latest`, `/api/history?days=1..366`, `/api/analytics`, `/api/alerts`, and authenticated POST `/api/refresh`. Its CLI imports and recalculates data. Prediction does not invoke its write paths. The public history endpoint was read only as an independent verification source, not as a production fallback.

Configure the existing database URL securely in `.env` locally or Render's environment variables. `.env` is ignored by Git. The URL may be `postgresql://`, `postgres://`, or SQLAlchemy's `postgresql+psycopg://`/`postgresql+psycopg2://`; the driver normalizes the scheme. Use TLS for a remote database. A SELECT-only database role can further enforce the application's read-only boundary if one already exists.

Run `.venv/bin/python scripts/check_database.py` or explicitly enable the integration test with `RUN_LIVE_DATABASE_TESTS=1 .venv/bin/python -m pytest tests/test_live_database.py -q`. These checks target the existing database and never clear tables or seed data.
