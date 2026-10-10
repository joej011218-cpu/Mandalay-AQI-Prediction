# Separate dashboard navigation changes after deployment approval

Neither existing dashboard repository was changed by this task.

For the existing Mandalay dashboard, set its already-supported environment variables:

```text
PREDICTION_URL=https://YOUR-PREDICTION-SERVICE.onrender.com/prediction.html
PREDICTION_AQI_STANDARD=cpcb-2014-rolling-v1
```

Its source requires both values before showing the prediction link. Enter the actual approved deployed URL; this placeholder is not a working service.

For the Vadodara dashboard at https://aiot-public-dashboard-2.onrender.com/, add a navigation link using its existing navigation styles and the actual deployed prediction URL:

```html
<a class="nav-link" href="https://YOUR-PREDICTION-SERVICE.onrender.com/prediction.html">Mandalay Prediction</a>
```

This is a separate navigation-only change to review in that repository. No changes to its database, model files, CPCB calculation or current data flow are needed. The prediction application already links to both dashboards and its own local precautions page.
