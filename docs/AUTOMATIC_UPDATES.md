# Automatic hourly source updates and five-minute display polling

## What is verified

The existing dashboard repository at commit `8480f6d263b54ac36731dbfd595e2909a95f4fed` defines a Render cron named `mandalay-aqi-hourly`:

- Repository: `https://github.com/joej011218-cpu/Mandalay-AQI-Dashboard`.
- Schedule: `5 * * * *` (UTC), once per hour. This corresponds to minute **35** of each Myanmar local hour.
- Build: `pip install -r requirements.lock.txt`.
- Start: `flask --app wsgi refresh-data`.
- Environment: the existing Mandalay `DATABASE_URL`, Python `3.12.14`.

Its actual `refresh-data` command calls the dashboard's existing Open-Meteo fetcher at Mandalay coordinates **21.9588, 96.0891**, timezone Asia/Yangon. It validates units, rejects future records and atomically saves raw readings and rebuilt CPCB results. That write path belongs to the existing dashboard; this prediction app never invokes it.

A cron definition does **not** prove an operational deployment. Render cron run logs and service status were not accessible through the configured tools. During final local verification the database's newest canonical observation remained **10 Oct 2026, 1:00 PM**, more than three hours behind the request. This establishes delayed data, not the cause of the delay. Do not treat the hourly scheduler as operationally verified.

## Inspect the existing job first

In Render, select the existing `mandalay-aqi-hourly` cron if present. Verify:

1. It targets the **Mandalay dashboard repository**, not the prediction repository.
2. The schedule, build command and start command match the values above.
3. `DATABASE_URL` targets the same existing Mandalay PostgreSQL database. Never create another database.
4. Recent scheduled runs show successful exits and the log `Imported ... Mandalay hourly readings; CPCB results recalculated`.
5. After a scheduled successful run, the existing dashboard `/api/latest` and prediction `/api/latest` advance to a recent whole-hour Mandalay observation and agree on CPCB AQI.

A manually successful run proves the command works, but confirm a later scheduled run as well. Existing record refreshes should occur through the already authorized dashboard's normal maintenance process. No manual run or dashboard database writes were performed by this task.

## Only if the job is absent or failed

After the UI is approved and deployment work is authorized, configure or repair **one** Render cron on the dashboard repository:

| Render setting | Value |
| --- | --- |
| Name | `mandalay-aqi-hourly` |
| Repository | `joej011218-cpu/Mandalay-AQI-Dashboard` |
| Runtime | Python |
| Root directory | Empty (repository root) |
| Schedule | `5 * * * *` |
| Build command | `pip install -r requirements.lock.txt` |
| Start command | `flask --app wsgi refresh-data` |
| `PYTHON_VERSION` | `3.12.14` |
| `DATABASE_URL` | Same existing Mandalay database URL, supplied securely |

Use the existing database's internal URL only when the cron is in a compatible Render private network/region. Otherwise use a reachable TLS-enabled external URL. Do not reuse the dashboard's full Blueprint to provision a second database. Do not add an independent collector or a public POST refresh endpoint to the prediction service. No new cron was created during this task.

See [Render cron documentation](https://render.com/docs/cronjobs) for schedule and run-log configuration.

## Prediction service behavior

- A browser sends read-only GET requests to `/api/latest` and `/api/prediction` every **300,000 ms**. A single-flight guard and focus/visibility coalescing prevent overlapping or rapid duplicate polls. Returning to a background tab triggers a fresh check when appropriate.
- PostgreSQL snapshots cache for 60 seconds per Gunicorn worker. A subsequent request sees newly stored observations. No daily manual script or prediction-side collector is required.
- Forecasts cache by **(observation timestamp, SHA-256 model-bank version, concentration-history fingerprint)**. The history fingerprint also detects provider corrections at an unchanged origin; storage calculation times do not invalidate it. The model version covers the bytes of all models, configs and ordered feature files. The model bank loads once at worker startup.
- Concurrent requests for the same origin share the inference lock. The 24 models run once for that key; repeated requests and five-minute polls reuse the result and preserve its actual `generated_at`.
- A new valid hourly origin triggers feature generation and all 24 horizon models once. No visitor clock is used as a forecast origin. Tests exercise two genuine successive observations and concurrent requests.
- A database outage retains an available in-memory snapshot and last forecast, with explicit warning; `/api/health` reports the source outage. The last successful observation and forecast generation timestamps stay visible. With no prior snapshot, the API returns 503.
- A new observation with incomplete features retains the prior successful forecast and labels it stale, with separate `latest_observation` metadata. Missing features are never filled.
- On cold start, complete real history at an old origin may still generate a forecast, but `status: stale`, `stale: true`, and warnings clearly identify its age. Those forecast timestamps remain anchored to the delayed observation; some hours may already have passed. This is not presented as a new current-origin forecast.
- The browser retains its last successful displayed forecast during an API failure and prominently labels the issue. It preserves the theme and updates the **existing** Chart.js instance.
- Cache is process-local and does not persist through a restart or synchronize multiple workers. The included deployment uses one worker with four threads. After restart, inference runs again for the first requested valid origin and records a new actual generation time.

Prediction APIs are public read-only. Frontend JavaScript never receives database credentials and never calls administrative write endpoints. Production Render availability and operational scheduled refresh remain to be verified after approval and deployment.
