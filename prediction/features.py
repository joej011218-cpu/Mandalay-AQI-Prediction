"""Normalize real observations and reproduce the saved training feature pipeline."""
import warnings
import numpy as np
import pandas as pd
from .training_features import calculate_targets, build_features

MAPPING = {'pm2_5':'pm25', 'pm10':'pm10', 'carbon_monoxide':'co_ug_m3',
           'nitrogen_dioxide':'no2_ug_m3', 'sulphur_dioxide':'so2_ug_m3', 'ozone':'o3_ug_m3'}
HISTORY_HOURS = 192

class DataUnavailable(ValueError):
    pass


def prepare(rows):
    if not rows:
        raise DataUnavailable('No canonical Mandalay observations available')
    raw = pd.DataFrame(rows)
    # DB timestamps must be aware; never silently reinterpret UTC or local time.
    if any(pd.Timestamp(t).tzinfo is None for t in raw['timestamp']):
        raise DataUnavailable('Observation timestamps must include timezone offsets')
    raw['timestamp'] = pd.to_datetime(raw['timestamp'], utc=True).dt.tz_convert('Asia/Yangon')
    raw = raw.sort_values('timestamp')
    if raw.timestamp.duplicated().any():
        raise DataUnavailable('Duplicate observation timestamps')
    ts = raw.timestamp.dt
    if ((ts.minute != 0) | (ts.second != 0) | (ts.microsecond != 0)).any():
        raise DataUnavailable('Observations must be on Yangon whole-hour slots')
    raw = raw.rename(columns=MAPPING)
    for col in MAPPING.values():
        if col not in raw:
            raise DataUnavailable(f'Missing pollutant column: {col}')
        raw[col] = pd.to_numeric(raw[col], errors='coerce')
        raw.loc[(raw[col] < 0) | ~np.isfinite(raw[col]), col] = np.nan
    raw = raw.set_index('timestamp').asfreq('h').reset_index()
    raw['no2'] = raw.no2_ug_m3.astype(float)
    raw['so2'] = raw.so2_ug_m3.astype(float)
    raw['o3'] = raw.o3_ug_m3.astype(float)
    raw['co'] = raw.co_ug_m3.astype(float) / 1000.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', pd.errors.PerformanceWarning)
        data, columns = build_features(calculate_targets(raw))
    return data, columns


def inference_row(rows, expected_columns):
    data, columns = prepare(rows)
    if len(data) < HISTORY_HOURS:
        raise DataUnavailable('Incomplete history: requires 192 hourly slots to reproduce the full CPCB window at the 168-hour AQI lag')
    if columns != expected_columns:
        raise DataUnavailable('Feature names or order differ from saved models')
    last = data.iloc[-1]
    missing = [name for name in columns if not np.isfinite(last[name])]
    if not np.isfinite(last['aqi']):
        raise DataUnavailable('Current numeric CPCB AQI unavailable (missing readings or open Severe band)')
    if missing:
        raise DataUnavailable(f'Incomplete history: {len(missing)} unavailable features; first: {", ".join(missing[:8])}. Requires up to 192 hourly slots; missing data are never filled.')
    x = data[columns].iloc[[-1]].astype('float32')
    if not np.isfinite(x.to_numpy()).all():
        raise DataUnavailable('Features overflow float32')
    return last, x
