
/* ============================================================
   API CONFIGURATION
\============================================================ */
const API_BASE = "";
let forecastChart = null;
let latestPredictions = [];
let modalReturnFocus=null;
/* ============================================================
   THEME
\============================================================ */
const themeToggle =
  document.getElementById("themeToggle");
function isLightMode() {
  return document.body.classList.contains("light-mode");
}
function updateThemeButton() {
  if (isLightMode()) {
    themeToggle.textContent = "🌙 Dark Mode";
  } else {
    themeToggle.textContent = "☀️ Light Mode";
  }
}
function applySavedTheme() {
  const savedTheme =
    localStorage.getItem("aqi-theme");
  if (savedTheme === "light") {
    document.body.classList.add("light-mode");
  } else {
    document.body.classList.remove("light-mode");
  }
  updateThemeButton();
}
themeToggle.addEventListener(
  "click",
  function() {
    document.body.classList.toggle(
      "light-mode"
    );
    localStorage.setItem(
      "aqi-theme",
      isLightMode()
        ? "light"
        : "dark"
    );
    updateThemeButton();
    if (
      latestPredictions.length
      && typeof Chart !== "undefined"
    ) {
      drawForecastChart(latestPredictions);
    }
  }
);
applySavedTheme();
/* ============================================================
   AQI CATEGORY
\============================================================ */
function getCategory(aqi) {
  if (
    aqi === null ||
    aqi === undefined ||
    isNaN(aqi)
  ) {
    return "Unavailable";
  }
  aqi = Number(aqi);
  if (aqi <= 50) return "Good";
  if (aqi <= 100) return "Satisfactory";
  if (aqi <= 200) return "Moderate";
  if (aqi <= 300) return "Poor";
  if (aqi <= 400) return "Very Poor";
  return "Severe";
}
/* ============================================================
   AQI COLOR
\============================================================ */
function getColor(aqi) {
  if (
    aqi === null ||
    aqi === undefined ||
    isNaN(aqi)
  ) {
    return "#8A97A0";
  }
  aqi = Number(aqi);
  if (aqi <= 50) return "#4E9F3D";
  if (aqi <= 100) return "#A8C43A";
  if (aqi <= 200) return "#E8C547";
  if (aqi <= 300) return "#E8823C";
  if (aqi <= 400) return "#D8453B";
  return "#7A2A2A";
}
/* ============================================================
   FORMAT TIMESTAMP
\============================================================ */
function formatTime(timestamp) {
  if (!timestamp || !/(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp)) return "—";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "—";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone:"Asia/Yangon",day:"numeric",month:"short",year:"numeric",
    hour:"numeric",minute:"2-digit",hour12:true
  }).formatToParts(date);
  const part = name => parts.find(p=>p.type===name)?.value || "";
  return `${part("day")} ${part("month")} ${part("year")}, ${Number(part("hour"))}:${part("minute")} ${part("dayPeriod").toUpperCase()}`;
}
function bindCategory(element, handler) {
  element.setAttribute("role","button"); element.tabIndex=0;
  element.onclick=handler;
  element.onkeydown=event=>{if(event.key==="Enter" || event.key===" "){event.preventDefault();handler();}};
}
function getPrecautionInfo(aqi) {
  const category = getCategory(aqi);
  const guidance = {
    "Good": {
      message: "Air quality is considered good and poses little or no risk for most people.",
      actions: [
        "Normal outdoor activities can continue.",
        "Outdoor exercise and recreation can continue as usual.",
        "Continue normal daily activities."
      ]
    },
    "Satisfactory": {
      message: "Air quality is generally acceptable. Sensitive people may experience minor breathing discomfort.",
      actions: [
        "Normal activities can continue for most people.",
        "Sensitive people should monitor for breathing discomfort.",
        "Reduce prolonged or strenuous outdoor exertion if discomfort occurs."
      ]
    },
    "Moderate": {
      message: "Breathing discomfort may occur in people with lung, asthma or heart conditions, especially during prolonged exposure.",
      actions: [
        "Sensitive groups should consider reducing prolonged or strenuous outdoor activity.",
        "Take additional breaks during outdoor physical activity.",
        "Move indoors if coughing, wheezing or breathing discomfort occurs."
      ]
    },
    "Poor": {
      message: "Prolonged exposure may cause breathing discomfort, particularly for people with respiratory or heart conditions.",
      actions: [
        "Reduce prolonged or strenuous outdoor physical activity.",
        "Sensitive groups should minimize outdoor exertion.",
        "Consider moving exercise and other strenuous activities indoors."
      ]
    },
    "Very Poor": {
      message: "Prolonged exposure can cause respiratory illness or significant breathing discomfort.",
      actions: [
        "Avoid strenuous outdoor physical activity.",
        "Sensitive groups should remain indoors as much as practical.",
        "Keep outdoor exposure as short as reasonably possible."
      ]
    },
    "Severe": {
      message: "Air quality may affect healthy people and can seriously affect people with existing respiratory or cardiovascular conditions.",
      actions: [
        "Avoid outdoor physical activity where possible.",
        "Minimize exposure to outdoor air, especially for sensitive groups.",
        "Move strenuous activities indoors and reduce unnecessary outdoor exposure."
      ]
    },
    "Unavailable": {
      message: "Health guidance is unavailable because a valid AQI value was not provided.",
      actions: ["Check the latest CPCB observation before planning outdoor activity."]
    }
  };
  return guidance[category] || guidance["Unavailable"];
}
function showPrecautionModal(aqi, timestamp, horizonLabel, valueLabel = "Predicted AQI") {
  const numericAQI = aqi == null ? NaN : Number(aqi);
  const validAQI = Number.isFinite(numericAQI);
  const category = getCategory(numericAQI);
  const info = getPrecautionInfo(numericAQI);
  const color = getColor(numericAQI);
  document.getElementById("precautionCategory").textContent = category;
  document.getElementById("precautionCategory").style.background = color;
  document.getElementById("precautionAQI").textContent =
    valueLabel + ": " + (validAQI ? numericAQI.toFixed(1) : "—");
  document.getElementById("precautionMessage").textContent = info.message;
  const list = document.getElementById("precautionList");
  list.innerHTML = "";
  info.actions.forEach(action => {
    const li = document.createElement("li");
    li.textContent = action;
    list.appendChild(li);
  });
  let meta = horizonLabel ? horizonLabel + (valueLabel === "Current AQI" ? "" : " forecast") : "AQI guidance";
  if (timestamp) meta += " • " + formatTime(timestamp);
  meta += " • Guidance is based on the AQI value shown for this period.";
  document.getElementById("precautionMeta").textContent = meta;
  document.getElementById("precautionModal").classList.add("show");
  document.body.style.overflow = "hidden";
  modalReturnFocus=document.activeElement;
  document.getElementById("precautionClose").focus();
}
function closePrecautionModal() {
  document.getElementById("precautionModal").classList.remove("show");
  document.body.style.overflow = "";
  modalReturnFocus?.focus();
}
document.getElementById("precautionClose").addEventListener("click", closePrecautionModal);
document.getElementById("precautionModal").addEventListener("click", function(event) {
  if (event.target === this) closePrecautionModal();
});
document.addEventListener("keydown", function(event) {
  if (event.key === "Escape") closePrecautionModal();
});
/* ============================================================
   FORECAST SUMMARY CARD
\============================================================ */
function setSummaryCard(
  horizon,
  prediction
) {
  const valueElement =
    document.getElementById(
      "aqi" + horizon
    );
  const categoryElement =
    document.getElementById(
      "cat" + horizon
    );
  if (
    !prediction ||
    !valueElement ||
    !categoryElement
  ) {
    return;
  }
  const aqi =
    Number(
      prediction.predicted_aqi
    );
  if (isNaN(aqi)) {
    valueElement.textContent =
      "—";
    categoryElement.textContent =
      "Unavailable";
    categoryElement.style.background =
      "#8A97A0";
    return;
  }
  const color =
    getColor(aqi);
  valueElement.textContent =
    aqi.toFixed(1);
  valueElement.style.color =
    color;
  categoryElement.textContent =
    getCategory(aqi);
  categoryElement.style.background =
    color;
  categoryElement.title = "Click to view health precautions";
  bindCategory(categoryElement, function() {
    showPrecautionModal(
      aqi,
      prediction.forecast_timestamp,
      "+" + horizon + "h",
      "Predicted AQI"
    );
  });
}
/* ============================================================
   FORECAST SUMMARY
\============================================================ */
function displayForecastSummary(
  predictions
) {
  function findPrediction(
    horizon
  ) {
    return predictions.find(
      item =>
        Number(
          item.horizon_hours
        ) === horizon
    );
  }
  setSummaryCard(
    1,
    findPrediction(1)
  );
  setSummaryCard(
    6,
    findPrediction(6)
  );
  setSummaryCard(
    12,
    findPrediction(12)
  );
  setSummaryCard(
    24,
    findPrediction(24)
  );
  document.getElementById(
    "forecastSummary"
  ).style.display =
    "grid";
}
/* ============================================================
   FORECAST CHART
\============================================================ */
function drawForecastChart(
  predictions
) {

  latestPredictions =
    predictions;
  const canvas =
    document.getElementById(
      "forecastChart"
    );
  const labels = predictions.map(prediction => [
    "+"+prediction.horizon_hours+"h",
    ...formatTime(prediction.forecast_timestamp).split(", ")
  ]);
  const values =
    predictions.map(
      prediction =>
        Number(
          prediction.predicted_aqi
        )
    );
  const pointColors =
    values.map(
      value =>
        getColor(value)
    );
  const textColor =
    isLightMode()
      ? "#66727B"
      : "#8A97A0";
  const legendColor =
    isLightMode()
      ? "#1D252B"
      : "#E8EDF0";
  const gridColor =
    isLightMode()
      ? "#D9E0E5"
      : "#2A333A";
  const config = {
        type: "line",
        data: {
          labels:
            labels,
          datasets: [
            {
              label:
                "Predicted AQI",
              data:
                values,
              borderColor:
                "#E8C547",
              backgroundColor:
                "rgba(232,197,71,0.12)",
              borderWidth:
                3,
              pointRadius:
                4,
              pointHoverRadius:
                6,
              pointBackgroundColor:
                pointColors,
              pointBorderColor:
                pointColors,
              tension:
                0.25,
              fill:
                true
            }
          ]
        },
        options: {
          responsive:
            true,
          maintainAspectRatio:
            false,
          interaction: {
            intersect:
              false,
            mode:
              "index"
          },
          plugins: {
            legend: {
              display:
                true,
              labels: {
                color:
                  legendColor
              }
            },
            tooltip: {
              callbacks: {
                title:
                  function(context) {
                    const index =
                      context[0]
                        .dataIndex;
                    return "+"+predictions[index].horizon_hours+"h · "+formatTime(predictions[index].forecast_timestamp)+" (Asia/Yangon)";
                  },
                afterBody:
                  function(context) {
                    const index =
                      context[0]
                        .dataIndex;
                    const prediction =
                      predictions[index];
                    const delta =
                      Number(
                        prediction.predicted_delta
                      );
                    return [
                      "Category: "
                      + getCategory(
                          prediction.predicted_aqi
                        ),
                      "Change: "
                      + (
                          delta >= 0
                            ? "+"
                            : ""
                        )
                      + delta.toFixed(2)
                    ];
                  }
              }
            }
          },
          scales: {
            x: {
              ticks: {
                color:
                  textColor,
                maxTicksLimit:
                  12,
                maxRotation: 0
              },
              grid: {
                color:
                  gridColor
              }
            },
            y: {
              beginAtZero:
                false,
              title: {
                display:
                  true,
                text:
                  "AQI",
                color:
                  textColor
              },
              ticks: {
                color:
                  textColor
              },
              grid: {
                color:
                  gridColor
              }
            }
          }
        }
      }
    ;
  if (forecastChart) {
    forecastChart.data=config.data;
    forecastChart.options=config.options;
    forecastChart.update("none");
  } else {
    forecastChart=new Chart(canvas,config);
  }
}
/* ============================================================
   FORECAST TABLE
\============================================================ */
function displayForecastTable(
  predictions
) {
  const tbody =
    document.getElementById(
      "forecastTableBody"
    );
  tbody.innerHTML =
    "";
  predictions.forEach(
    prediction => {
      const row =
        document.createElement(
          "tr"
        );
      const aqi =
        Number(
          prediction.predicted_aqi
        );
      const delta =
        Number(
          prediction.predicted_delta
        );
      let deltaClass =
        "";
      if (delta > 0) {
        deltaClass =
          "delta-positive";
      }
      if (delta < 0) {
        deltaClass =
          "delta-negative";
      }
      const deltaText =
        isNaN(delta)
          ? "—"
          :
            (
              delta >= 0
                ? "+"
                : ""
            )
            + delta.toFixed(2);
      row.innerHTML = `
        <td>
          +${prediction.horizon_hours}h
        </td>
        <td>
          ${formatTime(prediction.forecast_timestamp).split(", ")[0]}
        </td>
        <td>
          ${formatTime(prediction.forecast_timestamp).split(", ")[1] || "—"}
        </td>
        <td
          class="aqi-value"
          style="
            color:${getColor(aqi)};
          "
        >
          ${
            isNaN(aqi)
              ? "—"
              : aqi.toFixed(1)
          }
        </td>
        <td
          class="${deltaClass}"
        >
          ${deltaText}
        </td>
        <td>
          <button
            type="button"
            class="category-button"
            style="background:${getColor(aqi)};"
            title="Click to view health precautions"
          >
            ${getCategory(aqi)}
          </button>
        </td>
      `;
      const categoryButton = row.querySelector(".category-button");
      categoryButton.addEventListener("click", function() {
        showPrecautionModal(
          aqi,
          prediction.forecast_timestamp,
          "+" + prediction.horizon_hours + "h",
          "Predicted AQI"
        );
      });
      tbody.appendChild(
        row
      );
    }
  );
}
/* ============================================================
   CURRENT CPCB REFERENCE
\============================================================ */
function displayCurrent(data) {
  if (!data) {
    return;
  }
  const aqi = data.aqi == null ? NaN : Number(data.aqi);
  const currentAQI =
    document.getElementById("currentAQI");
  const currentCategory =
    document.getElementById("currentCategory");
  if (!isNaN(aqi)) {
    currentAQI.textContent =
      aqi.toFixed(1);
    currentAQI.style.color =
      getColor(aqi);
    currentCategory.textContent =
      getCategory(aqi);
    currentCategory.style.background =
      getColor(aqi);
    currentCategory.style.cursor = "pointer";
    currentCategory.title = "Click to view health precautions";
    bindCategory(currentCategory, function() {
      showPrecautionModal(
        aqi,
        data.timestamp,
        "Current air quality",
        "Current AQI"
      );
    });
  } else {
    currentAQI.textContent = "—";
    currentCategory.textContent = "Unavailable";
    currentCategory.style.background = "#8A97A0";
    currentCategory.onclick=null;
    currentCategory.onkeydown=null;
    currentCategory.removeAttribute("role");
    currentCategory.removeAttribute("tabindex");
  }
  document.getElementById("currentTime").textContent =
    data.timestamp
      ? formatTime(data.timestamp) + " · Mandalay"
      : "—";
  const units = {
    pm25: "µg/m³",
    pm10: "µg/m³",
    no2: "µg/m³",
    o3: "µg/m³",
    so2: "µg/m³",
    co: "mg/m³"
  };
  Object.keys(units).forEach(
    pollutant => {
      const element =
        document.getElementById(pollutant);
      if (!element) return;
      const value =
        data[pollutant];
      if (
        value === null ||
        value === undefined ||
        isNaN(value)
      ) {
        element.textContent = "—";
        return;
      }
      const decimalPlaces =
        pollutant === "co"
          ? 3
          : 1;
      element.textContent =
        Number(value).toFixed(decimalPlaces)
        + " "
        + units[pollutant];
    }
  );
}
/* ============================================================
   LOAD API DATA
\============================================================ */
async function readAPI(path, method="GET") {
  const response=await fetch(`${API_BASE}${path}`,{method,cache:"no-store",signal:AbortSignal.timeout(method==="POST"?110000:25000)});
  const data=await response.json();
  if(!response.ok) throw new Error(data.error || "Data service is temporarily unavailable");
  if(data.aqi_standard!=="Indian CPCB AQI" || data.calculation_version!=="cpcb-2014-rolling-v1" || data.city!=="Mandalay, Myanmar") throw new Error("Incompatible Mandalay CPCB data");
  return data;
}
function currentAdapter(data) {
  const reading=key=>data.pollutants?.[key]?.value ?? null;
  return {aqi:data.cpcb_aqi,timestamp:data.timestamp,pm25:reading("pm2_5"),pm10:reading("pm10"),
    no2:reading("nitrogen_dioxide"),o3:reading("ozone"),so2:reading("sulphur_dioxide"),
    co:reading("carbon_monoxide")==null?null:reading("carbon_monoxide")/1000};
}
function showFreshness(forecast,current) {
  const el=document.getElementById("dataFreshness");
  const warnings=[...(forecast?.warnings || [])];
  if(current?.stale) warnings.push("Stale observation: the latest stored reading is delayed.");
  if(current?.warning) warnings.push(current.warning);
  el.classList.toggle("stale",warnings.length>0);
  const text=["Mandalay, Myanmar",current?.timestamp?"Observation: "+formatTime(current.timestamp):"Observation unavailable"];
  if(forecast?.generated_at) text.push("Forecast generated: "+formatTime(forecast.generated_at));
  if(warnings.length) text.push(...new Set(warnings));
  else text.push("Automatic display refresh every 5 minutes");
  text.push("Last checked: "+formatTime(new Date().toISOString()));
  el.textContent=text.join(" • ");
}
function clearCurrent() {
  const badge=document.getElementById("currentCategory");
  document.getElementById("currentAQI").textContent="—";badge.textContent="Unavailable";badge.style.background="#8A97A0";
  badge.onclick=null;badge.onkeydown=null;badge.removeAttribute("role");badge.removeAttribute("tabindex");
  document.getElementById("currentTime").textContent="Observation unavailable";
  for(const key of ["pm25","pm10","no2","o3","so2","co"])document.getElementById(key).textContent="—";
}
let lastDisplayedForecast=null;
async function loadForecast(manual=false) {
  const loading=document.getElementById("forecastLoading"),chartWrapper=document.getElementById("chartWrapper"),errorBox=document.getElementById("errorBox");
  const [latestResult,forecastResult]=await Promise.allSettled(manual?
    [Promise.resolve(null),readAPI("/api/prediction/refresh","POST")]:
    [readAPI("/api/latest"),readAPI("/api/prediction")]);
  let current=latestResult.status==="fulfilled"?latestResult.value?.data:null;
  if(forecastResult.status==="fulfilled") {
    const forecast=forecastResult.value;
    const predictions=(forecast.forecasts || []).map(item=>({...item,horizon_hours:Number(item.horizon),
      predicted_aqi:item.predicted_cpcb_aqi,forecast_timestamp:item.timestamp,forecast_origin:forecast.forecast_origin})).sort((a,b)=>a.horizon_hours-b.horizon_hours);
    if(predictions.length!==24 || predictions.some((p,i)=>p.horizon_hours!==i+1 || !Number.isFinite(p.predicted_aqi) ||
        formatTime(p.forecast_timestamp)==="—" || Date.parse(p.forecast_timestamp)!==Date.parse(forecast.forecast_origin)+p.horizon_hours*3600000)) {
      const warning="The backend returned an incomplete forecast or inconsistent target times. Keeping the previous prediction.";
      errorBox.textContent=warning;errorBox.style.display="block";
      setPredictionRefreshMessage("error",warning);
      return;
    }
    current=current || forecast.latest_observation || forecast.current;
    displayCurrent(currentAdapter(current));
    displayForecastSummary(predictions);displayForecastTable(predictions);
    lastDisplayedForecast=forecast;
    const refreshStatus=forecast.manual_refresh?.status;
    const message=refreshStatus==="cooldown"?"Showing the cached forecast; another source check is available in "+forecast.manual_refresh.retry_after+" seconds. ":
      refreshStatus==="unchanged"?"Source check completed; forecast inputs are unchanged. ":
      refreshStatus==="updated"?"Prediction updated successfully. ":"";
    document.getElementById("predictionUpdate").textContent="Last successful forecast generation: "+formatTime(forecast.generated_at)+" (Asia/Yangon)";
    if(manual)setPredictionRefreshMessage(refreshStatus==="updated" || refreshStatus==="unchanged"?"success":"idle",message || "Forecast loaded; no completed source update was confirmed.");
    chartWrapper.style.display="block";
    if(typeof Chart!=="undefined") drawForecastChart(predictions);
    else {chartWrapper.style.display="none";errorBox.textContent="Chart library unavailable; forecasts remain in the table.";errorBox.style.display="block";}
    loading.style.display="none";
    document.getElementById("forecastOrigin").textContent="Latest observation: "+formatTime(current.timestamp)+" • Forecast origin: "+formatTime(forecast.forecast_origin)+" • Generated: "+formatTime(forecast.generated_at)+" • All target times use Asia/Yangon. Targets are observation time +1 to +24 hours, not the button click time.";
    if(typeof Chart!=="undefined")errorBox.style.display="none";
    showFreshness(forecast,current);
  } else {
    const warning=forecastResult.reason.message;
    if(current)displayCurrent(currentAdapter(current));
    else if(!lastDisplayedForecast)clearCurrent();
    loading.textContent=lastDisplayedForecast?"Showing the last successful forecast.":"Unable to load prediction.";
    loading.style.display="block";
    errorBox.textContent="Data unavailable: "+warning+(lastDisplayedForecast?" • Displayed forecasts retain their original observation and generation times.":"");
    errorBox.style.display="block";
    if(manual)setPredictionRefreshMessage("error",warning+(lastDisplayedForecast?" Showing the last successful forecast.":""));
    showFreshness({...lastDisplayedForecast,warnings:[warning]},current || lastDisplayedForecast?.current);
  }
}
function setPredictionRefreshMessage(state,message) {
  const el=document.getElementById("predictionRefreshMessage");
  el.setAttribute("data-state",state);
  el.textContent=message;
}
async function manualRefreshPrediction() {
  if(refreshInProgress) return;
  refreshInProgress=true;
  const button=document.getElementById("refreshPrediction");
  button.disabled=true;
  button.setAttribute("aria-busy","true");
  document.getElementById("refreshPredictionLabel").textContent="Updating Prediction…";
  setPredictionRefreshMessage("loading","Checking the latest observations and updating prediction…");
  try {
    await loadForecast(true);
  } catch(error) {
    const errorBox=document.getElementById("errorBox");
    errorBox.textContent="Prediction refresh failed. "+error.message+(lastDisplayedForecast?" Showing the last successful forecast.":"");
    errorBox.style.display="block";
    setPredictionRefreshMessage("error","Prediction refresh failed. Showing the previous forecast.");
  } finally {
    button.disabled=false;
    button.setAttribute("aria-busy","false");
    document.getElementById("refreshPredictionLabel").textContent="Refresh Prediction";
    refreshInProgress=false;
  }
}
document.getElementById("refreshPrediction").addEventListener("click",manualRefreshPrediction);
/* Automatic polling continues to use the existing read-only APIs. */
const PAGE_REFRESH_MS = 5 * 60 * 1000;
let refreshInProgress = false;
let lastPollAt=0;
async function autoRefreshPrediction() {
  if (refreshInProgress || (lastPollAt && Date.now()-lastPollAt<10000)) {
    return;
  }
  refreshInProgress = true;
  lastPollAt=Date.now();
  try {
    await loadForecast();
  } catch (error) {
    console.error(
      "Forecast display refresh failed:",
      error
    );
  } finally {
    refreshInProgress = false;
  }
}
/* Load the currently stored data immediately. */
autoRefreshPrediction();
/* Check the backend for newer stored data every 5 minutes. */
setInterval(
  autoRefreshPrediction,
  PAGE_REFRESH_MS
);
/* Reload stored data after returning to a background tab. */
document.addEventListener(
  "visibilitychange",
  () => {
    if (!document.hidden) {
      autoRefreshPrediction();
    }
  }
);
/* Reload stored data when the browser window receives focus. */
window.addEventListener(
  "focus",
  autoRefreshPrediction
);
