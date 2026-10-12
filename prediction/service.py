from datetime import datetime, timezone
from copy import deepcopy
from hashlib import sha256
import threading
import time
import pandas as pd
from .cpcb import VERSION, POLLUTANTS, calculate, category, color, PRECAUTIONS
from .features import DataUnavailable, inference_row

META = dict(city='Mandalay, Myanmar', aqi_standard='Indian CPCB AQI', calculation_version=VERSION,
            timezone='Asia/Yangon', modeled_data=True,
            data_source='Existing Mandalay dashboard PostgreSQL / Open-Meteo CAMS')

class RefreshLimited(Exception):
    def __init__(self, message, retry_after):
        super().__init__(message)
        self.retry_after = retry_after

class ForecastService:
    def __init__(self, store, registry=None, model_error=None, max_age_hours=3, cache_seconds=60):
        self.store, self.registry, self.model_error = store, registry, model_error
        self.max_age_hours, self.cache_seconds = max_age_hours, cache_seconds
        self._cache = None
        self._expires = 0
        self._lock = threading.Lock()
        self._forecast_lock = threading.Lock()
        self._forecasts = {}
        self._last_forecast = None
        self.source_error = None
        self._refresh_after = 0

    def refresh(self, source_refresh):
        """One synchronous collector call per five minutes, including failures.

        The Render command uses one worker with four threads. Share its existing
        inference lock rather than creating a second inference pipeline.
        """
        if not self._forecast_lock.acquire(blocking=False):
            raise RefreshLimited('Prediction update is already running; try again shortly', 5)
        try:
            remaining = max(0, int(self._refresh_after - time.monotonic() + 1))
            if remaining:
                if self._last_forecast is None:
                    raise RefreshLimited('Please wait before refreshing again', remaining)
                result = self._cached_result(self._last_forecast, self._last_forecast['current'])
                result['manual_refresh'] = dict(status='cooldown', retry_after=remaining)
                return result
            self._refresh_after = time.monotonic() + 300
            with self._lock:
                previous = (self._cache, self._expires, self.source_error)
            try:
                source_refresh()
                with self._lock:
                    self._expires = 0
                result = self._forecast_locked(strict=True)
                if self.source_error:
                    raise DataUnavailable('Source refreshed but PostgreSQL observations could not be read')
                if result.get('latest_observation', result['current'])['timestamp'] != result['forecast_origin']:
                    raise DataUnavailable('New observations cannot produce a complete forecast; keeping the last successful prediction')
            except Exception:
                # The last forecast is only replaced after successful inference.
                # Restore the successful observation snapshot as well.
                with self._lock:
                    self._cache, self._expires, self.source_error = previous
                raise
            result['manual_refresh'] = dict(status='unchanged' if result['cached'] else 'updated', retry_after=300)
            return result
        finally:
            self._forecast_lock.release()

    def snapshot(self):
        with self._lock:
            if self._cache is None or time.monotonic() >= self._expires:
                try:
                    self._cache = self.store.fetch()
                    self.source_error = None
                except DataUnavailable as exc:
                    self.source_error = str(exc)
                    if not self._cache:
                        raise
                self._expires = time.monotonic()+self.cache_seconds
            return self._cache

    def latest(self, rows=None):
        rows = self.snapshot() if rows is None else rows
        if not rows:
            raise DataUnavailable('No canonical Mandalay observations available')
        row = rows[-1]
        at = pd.Timestamp(row['timestamp'])
        if at.tzinfo is None:
            raise DataUnavailable('Database timestamps must be timezone-aware')
        now = datetime.now(timezone.utc)
        if at.to_pydatetime() > now:
            raise DataUnavailable('Future observations cannot be used for inference')
        age = (now-at.to_pydatetime()).total_seconds()/3600
        history = {pd.Timestamp(r['timestamp']).to_pydatetime():{p:r.get(p) for p in POLLUTANTS} for r in rows}
        detail = calculate(at.to_pydatetime(),history)
        if row.get('calculation_version') not in (None, VERSION):
            raise DataUnavailable('Stored CPCB methodology version differs from training')
        stored = row.get('stored_cpcb_aqi')
        if stored is not None and stored != detail['cpcb_aqi']:
            raise DataUnavailable('Stored CPCB AQI differs from inference calculation; inspect dashboard history')
        return dict(timestamp=at.tz_convert('Asia/Yangon').isoformat(),
                    pollutants={p:dict(value=row.get(p),unit='µg/m³') for p in POLLUTANTS},
                    source=row.get('source'), stale=age>self.max_age_hours,
                    age_hours=round(age,2), data_cache_fallback=bool(self.source_error),
                    warning=self.source_error, **detail)

    def forecast(self):
        with self._forecast_lock:
            return self._forecast_locked()

    def _cached_result(self, result, latest, warning=None, cached=True):
        result = deepcopy(result)
        origin = pd.Timestamp(result['forecast_origin'])
        age = (datetime.now(timezone.utc)-origin.to_pydatetime()).total_seconds()/3600
        warnings = [message for message in (warning,self.source_error) if message]
        if age > self.max_age_hours:
            warnings.append(f'Stale data: forecast origin is {age:.2f} hours old; forecast times remain anchored to the delayed observation')
        result.update(status='stale' if warnings else 'available',stale=bool(warnings),
                      warnings=warnings,cached=cached,latest_observation=latest,
                      forecast_age_hours=round(age,2))
        return result

    def _forecast_locked(self, strict=False):
        if self.registry is None:
            raise DataUnavailable(self.model_error or 'Models unavailable')
        rows = self.snapshot()
        latest = self.latest(rows)
        # Provider corrections can change history without advancing its origin.
        # Exclude storage/calculation timestamps so unchanged inputs reuse inference.
        inputs = tuple((str(row['timestamp']), *(row.get(p) for p in POLLUTANTS)) for row in rows)
        key = (latest['timestamp'],self.registry.version,sha256(repr(inputs).encode()).hexdigest())
        if key in self._forecasts:
            return self._cached_result(self._forecasts[key],latest)
        if latest['stale']:
            if self._last_forecast:
                return self._cached_result(self._last_forecast,latest,'Latest observation is stale; displaying the last successful forecast')
            # On cold start, real delayed history can still support an explicitly
            # stale forecast. Keep its old origin; never shift it to browser time.
        try:
            current, frame = inference_row(rows, self.registry.columns)
        except DataUnavailable as exc:
            if self._last_forecast and not strict:
                return self._cached_result(self._last_forecast,latest,f'New observation cannot generate a complete forecast: {exc}')
            raise
        if float(current.aqi) != latest['cpcb_aqi']:
            raise DataUnavailable('Training target calculation differs from latest CPCB calculation')
        try:
            deltas = self.registry.predict(frame)
        except (ValueError,RuntimeError) as exc:
            raise DataUnavailable('Pretrained model inference failed; inspect artifact and library compatibility') from exc
        origin = current.timestamp
        forecasts = []
        for h,delta in deltas.items():
            raw = float(current.aqi)+delta
            bounded = max(0.,min(500.,raw)) # Training evaluation clips to CPCB reporting range.
            label = category(bounded)
            forecasts.append(dict(horizon=h,timestamp=(origin+pd.Timedelta(hours=h)).isoformat(),
                predicted_delta=delta,raw_predicted_cpcb_aqi=raw,predicted_cpcb_aqi=bounded,
                clipped=bounded != raw,category=label,color=color(label),precautions=PRECAUTIONS[label]))
        result = dict(**META,status='available',forecast_origin=origin.isoformat(),
                    generated_at=datetime.now(timezone.utc).astimezone(origin.tzinfo).isoformat(),
                    current=latest,forecasts=forecasts,feature_count=len(frame.columns),
                    model_version=self.registry.version,stale=False,cached=False,warnings=[],
                    limitation='Modeled CAMS data; model forecast, not an official station AQI. No prediction intervals are available.')
        self._forecasts = {key:result}
        self._last_forecast = result
        if self.source_error or latest['stale']:
            return self._cached_result(result,latest,cached=False)
        return deepcopy(result)
