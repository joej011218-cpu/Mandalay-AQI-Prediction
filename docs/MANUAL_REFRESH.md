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
  Source failures return sanitized HTTP 502/503/504 diagnostics as listed below;
  database/known inference failures return HTTP 503, and unexpected failures
  return HTTP 500. The previous forecast and its generation time remain
  displayed. Automatic polling continues after the button finishes.

The response now includes safe `error_code` diagnostics for source failures:

| Code | HTTP | Action |
| --- | --- | --- |
| `dashboard_token_missing` | 503 | Set `DASHBOARD_REFRESH_TOKEN` on Prediction in Render. |
| `dashboard_authorization_failed` | 503 | Securely verify it matches Dashboard's existing `REFRESH_TOKEN`. |
| `dashboard_timeout` | 504 | Check Dashboard availability and retry after cooldown. |
| `dashboard_unavailable` | 502 | Check Dashboard service status. |
| `dashboard_not_completed` | 502 | Verify Dashboard runs its synchronous refresh deployment; 202 is not completion. |
| `dashboard_invalid_response` | 502 | Check the Dashboard's response contract. |

Render logs record only these reason codes. Upstream bodies, exception messages,
tokens, and request headers are never logged or returned. The previous generic
message obscured these causes, and a broad `ValueError` catch also masked the
source client's own diagnostic errors. Those defects are corrected. Missing
local credentials do not establish the cause of a live Render failure; use the
actual deployed endpoint's error code to confirm that cause.

## Forecast display and automatic workflow

The refresh panel sits below navigation and above Current Air Quality, with
responsive light/dark styling, keyboard focus, loading spinner, and a separate
status message. All 24 rows show the horizon, target date, target Yangon time,
AQI, category, and category color; the four summary cards remain. Chart labels
and tooltips show target dates and times without changing the line styling.

Each validated model configuration declares its horizon `h` and its target as
future CPCB AQI minus current CPCB AQI. The service therefore computes targets
as **latest hourly observation timestamp + h hours**. Generation time and click
time never shift those targets. At a generation time of 9:06 PM with a 9:00 PM
observation, +1h means 10:00 PM. If the observation is older, the old origin
and stale-data warning remain visible rather than relabeling old forecasts.

The Prediction repository contains no hourly collector/scheduler or durable
background forecast job; its models run on demand against observations written
by the existing Dashboard workflow. This change does not alter that external
hourly source schedule or the existing five-minute/focus/visibility polling.
Manual calls share Prediction's existing inference lock; they do not reset any
external timer or cancel scheduled collection. PostgreSQL access in Prediction
remains read-only, and the existing collector retains responsibility for atomic
source writes and CPCB recalculation.

## Validation

```sh
pip install -r requirements-dev.txt
python -m pytest tests/test_manual_refresh.py -q
node scripts/test_frontend.cjs
# With a local Prediction server running; browser API responses are mocked:
node scripts/test_browser.cjs
python scripts/check_deployment.py
python scripts/validate_models.py
```

The Python workflow tests use a captured real Mandalay history fixture and the
actual 24 models, with mocked source/network/database boundaries. The fixture was
copied from the repository's existing validation branch at commit `cfe0fbac`.
The JavaScript harness checks rendering, manual POST/loading/singleflight/error
retention, unchanged chart reuse, Yangon times, and automatic polling.
The Chromium checks exercise desktop/tablet/mobile in both themes, button hover
and focus, spinner/disabled states, all 24 targets, midnight transitions, and
failed refresh retention. Install Playwright locally when unavailable; the
browser script uses `/usr/bin/chromium` or `CHROMIUM_PATH`. The default local
server URL is `http://127.0.0.1:8015`, overridable with `PREDICTION_TEST_URL`.

These checks do not establish live Dashboard authorization or Render deployment
readiness. Those require the server-side token, live database binding, and the
post-deployment browser check above. No production refresh or database write is
performed by the local tests.
