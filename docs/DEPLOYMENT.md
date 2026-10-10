# Exact Render deployment steps

Deployment preparation is complete; review these results before publishing. Publication to GitHub is authorized. Render service creation and deployment are left to the user.

## 1. Publish application files and pretrained artifacts

The measured bundle contains 74 files (72 joblib artifacts, manifest and evaluation CSV), totaling **18,791,906 bytes**. Its largest file is **793,964 bytes**, well below GitHub's per-file 100 MiB block threshold. These particular models can therefore be included directly in this repository. No LFS or model download service is required for the current bundle.

The deployment commit includes the Flask runtime, original frontend, configuration, checksum inventory, validation scripts and the **entire** `models/XGB_Mandalay_CPCB_Delta24_2026/` directory. Model Git blobs were compared against the inventory before publication. Local tests, fixtures, screenshots and training references are excluded from the deployment commit. `.env` and `.venv` remain ignored; credentials must be supplied in Render settings.

If future artifacts exceed GitHub's limit, distribute the trusted bundle through release assets or object storage, download it at build time with checksum verification, and set `MODEL_DIR` to the extracted directory. Do not commit oversized artifacts or execute training as a substitute. That alternative is not configured here because the current bundle fits.

## 2. Create the web service

In Render select **New → Blueprint**, connect the published repository, and use its root `render.yaml`. It creates one Python web service and no database. The included plan is `starter`; select the intended service plan when reviewing Render's setup.

Alternatively select **New → Web Service**, connect the repository, and enter:

| Setting | Exact value |
| --- | --- |
| Runtime | Python |
| Root directory | Leave empty (repository root) |
| Build command | `pip install -r requirements.txt && python scripts/check_deployment.py && python scripts/validate_models.py` |
| Start command | `gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120` |
| Health check path | `/api/health` |
| `PYTHON_VERSION` | `3.11.11` |
| `MODEL_DIR` | `models/XGB_Mandalay_CPCB_Delta24_2026` |
| `DATABASE_URL` | Existing Mandalay PostgreSQL connection URL, entered securely |
| `MANDALAY_DASHBOARD_URL` | `https://mandalay-aqi-dashboard-bk49.onrender.com/` |
| `VADODARA_DASHBOARD_URL` | `https://aiot-public-dashboard-2.onrender.com/` |

If the existing database is on Render, use its internal URL only for a service in the same supported private network/region; otherwise use its reachable external URL with TLS. The local `.env` is not deployed. Enter credentials in Render's environment settings without adding them to source control or this table.

## 3. Validate the deployment

The build must log 24 loaded models, 198 features, and horizons 1–24. No fit/training call exists in that command. A missing bundle fails the build.

After deployment, open the generated service URL:

1. `/api/health` must return HTTP 200 with `models_loaded: 24` and `database: reachable`.
2. `/api/latest` must show recent real Mandalay concentrations and CPCB metadata.
3. `/api/prediction/status` must return `feature_count: 198` and `ready` for current data. A delayed origin returns explicitly `stale`; resolve its source-refresh delay before claiming a fresh live deployment.
4. `/api/prediction` must return 24 forecasts, horizons 1–24, with the same observation origin and Asia/Yangon offsets.
5. `/prediction.html` must preserve the original dark layout, theme toggle, Chart.js chart, four cards, 24 table rows, clickable categories and AM/PM timestamps.
6. `/precautions.html` must show the original six category cards and matching theme/navigation.
7. Confirm five-minute display polling, stable cached generation times for the same origin, and new forecasts after a later stored valid hourly observation.

Health means models and database reads work. Forecast readiness also requires a recent origin, 192 historical hourly slots, complete selected features and numeric CPCB AQI. Delayed data may still yield a clearly labeled stale forecast anchored to the actual old origin. If history is missing or older than three hours, use the **existing dashboard's** normal data maintenance workflow; this prediction app intentionally does not refresh or change its records. Render's deployment itself remains untested until these checks pass there.

To enable the existing Mandalay dashboard's prediction navigation, configure that dashboard's existing `PREDICTION_URL` to the new prediction HTTPS URL and `PREDICTION_AQI_STANDARD=cpcb-2014-rolling-v1`. This separate dashboard configuration was not changed by this task.

## 4. Existing hourly scheduler and cross-dashboard links

Follow [AUTOMATIC_UPDATES.md](AUTOMATIC_UPDATES.md) to inspect the existing hourly cron's **scheduled run logs** and configure or repair one dashboard-side job only if needed. Its repository definition alone is not proof that it runs. The prediction Blueprint deliberately creates no cron or database. Follow [DASHBOARD_LINKS.md](DASHBOARD_LINKS.md) for separate navigation changes after the actual prediction URL exists. Neither dashboard was modified.

References: [Render Flask deployment](https://render.com/docs/deploy-flask), [Python version](https://render.com/docs/python-version), [Blueprint reference](https://render.com/docs/blueprint-spec), [GitHub large-file limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

The checksum inventory `deployment-models.json` covers every bundle file. The build guard rejects missing, extra, or changed artifacts. The staged-index check additionally compares the exact Git blobs against that inventory before publication. Python is pinned in both `.python-version` and the Blueprint.
