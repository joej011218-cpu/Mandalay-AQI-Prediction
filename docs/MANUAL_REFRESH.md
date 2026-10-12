# Manual prediction refresh on Render

Only the Prediction application changes. The existing Dashboard collector,
PostgreSQL tables, automatic hourly schedule, and 24 trained XGBoost models
remain unchanged. No training, database migration, or background worker is needed.

## Render configuration

In the **Prediction web service**, set `DASHBOARD_REFRESH_TOKEN` securely to the
same value as the Dashboard service's existing `REFRESH_TOKEN`. Do not change
the Dashboard token or paste either value into source control, browser code,
URLs, screenshots, or chat. This is the only new environment variable.

Retain the existing `DATABASE_URL` (the same Mandalay PostgreSQL database) and
`MODEL_DIR=models/XGB_Mandalay_CPCB_Delta24_2026`. The existing
`MANDALAY_DASHBOARD_URL` and `VADODARA_DASHBOARD_URL` navigation settings are
unchanged and do not carry credentials. `PYTHON_VERSION` remains as configured
by the existing Blueprint.

Keep the existing build command:

```sh
pip install -r requirements.txt && python scripts/check_deployment.py && python scripts/validate_models.py
```

Keep **one web instance and one Gunicorn worker**, with four threads:

```sh
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120
```

The server lock, five-minute rate limit, and successful forecast cache are shared
by threads in that worker. They are process-local and reset on restart. Multiple
workers or instances would each have their own rate limit and cache; do not scale
this configuration without adding shared coordination. No paid background worker
is required. The existing web-service plan is unchanged.

Deploy the updated Prediction branch, then reload `/prediction.html`. In browser
network tools, verify reload uses `GET /api/latest` and `GET /api/prediction`,
without calling a source refresh. Click **Refresh Prediction** and verify
`POST /api/prediction/refresh` completes, the charts update, and the last
successful prediction update time is displayed in Asia/Yangon. Test again within
five minutes: it should reuse the forecast and report the remaining wait.

## Request behavior

- Reload and automatic five-minute polling use the existing read-only GET APIs.
  PostgreSQL snapshots normally cache for up to 60 seconds. A new observation,
  changed historical concentrations, or changed model version invalidates the
  inference cache. Reload does not trigger the expensive source collector.
- Button clicks call `POST /api/prediction/refresh` without a browser token. The
  server sends an authenticated HTTPS POST to the fixed existing Dashboard
  `/api/refresh` endpoint and waits for its synchronous HTTP 200 JSON result.
  Redirects, HTTP 202, oversized/invalid responses, and upstream errors are rejected.
- After source refresh, Prediction immediately rereads PostgreSQL and invokes its
  existing forecasting code with the trained models. Unchanged inputs reuse the
  successful forecast, including its original `generated_at` time. The current
  in-memory cache is retained; there is no new database forecast table.
- The same inference lock protects manual and automatic calculations. Concurrent
  manual calls receive HTTP 429 and `Retry-After`; no duplicate collector starts.
  Source checks are limited globally to one attempt per five minutes per worker,
  including failures. During cooldown, a saved forecast returns HTTP 200 with
  `manual_refresh.status=cooldown`; without a saved forecast the response is 429.
- Successful checks return `manual_refresh.status=updated` or `unchanged`.
  Source/database/known inference failures return a sanitized HTTP 503; unexpected
  failures return HTTP 500. The previous forecast and its generation time remain
  displayed. Automatic polling continues after the button finishes.

## Validation

```sh
pip install -r requirements-dev.txt
python -m pytest tests/test_manual_refresh.py -q
node scripts/test_frontend.cjs
python scripts/check_deployment.py
python scripts/validate_models.py
```

The Python workflow tests use a captured real Mandalay history fixture and the
actual 24 models, with mocked source/network/database boundaries. The fixture was
copied from the repository's existing validation branch at commit `cfe0fbac`.
The JavaScript harness checks rendering, manual POST/loading/singleflight/error
retention, unchanged chart reuse, Yangon times, and automatic polling.

These checks do not establish live Dashboard authorization or Render deployment
readiness. Those require the server-side token, live database binding, and the
post-deployment browser check above. No production refresh or database write is
performed by the local tests.
