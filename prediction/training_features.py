"""Inference-only functions copied verbatim from the original training script. No training entry point."""

import numpy as np
import pandas as pd
from .cpcb import calculate, VERSION

POLLUTANTS = ['pm25','pm10','co','no2','so2','o3']

AQI_LAGS = [1,2,3,6,12,24,48,72,168]

POLLUTANT_LAGS = [1,2,3,6,12,24,48,72,168]

ROLLING_WINDOWS = [3,6,12,24]

TREND_WINDOWS = [3,6,12]

CHANGE_LAGS = [1,3,6,12,24]

def calculate_targets(df):
    """Call the actual production CPCB logic, preserving missing values."""
    from .cpcb import POLLUTANTS as CPCB_KEYS
    mapping = {'pm2_5':'pm25','pm10':'pm10','carbon_monoxide':'co_ug_m3',
               'nitrogen_dioxide':'no2_ug_m3','sulphur_dioxide':'so2_ug_m3','ozone':'o3_ug_m3'}
    # UTC-aware dict keys avoid mixing different local or naive timestamp conventions.
    utc = df['timestamp'].dt.tz_convert('UTC')
    history = {t.to_pydatetime(): {key: (float(row[mapping[key]]) if pd.notna(row[mapping[key]]) else None)
                for key in CPCB_KEYS} for t,(_,row) in zip(utc,df.iterrows())}
    values = []
    for t in utc:
        result = calculate(t.to_pydatetime(), history)
        values.append(result['cpcb_aqi'])
    df = df.copy()
    df['aqi'] = pd.Series(values,dtype='float64')
    print('CPCB calculation:', VERSION, 'eligible rows:', df['aqi'].notna().sum(), '/', len(df))
    return df

def build_features(df):
    """Historical features available at forecast origin t, never t+h."""
    data = df.copy()
    features = []
    def add(name, series):
        data[name] = series
        features.append(name)
    for lag in AQI_LAGS:
        add(f'aqi_lag_{lag}',data['aqi'].shift(lag))
    for p in POLLUTANTS:
        for lag in POLLUTANT_LAGS:
            add(f'{p}_lag_{lag}',data[p].shift(lag))
    for w in ROLLING_WINDOWS:
        roll = data['aqi'].rolling(w,min_periods=w)
        for label,series in [('mean',roll.mean()),('max',roll.max()),('min',roll.min()),('std',roll.std())]:
            add(f'aqi_roll_{w}h_{label}',series)
    for p in POLLUTANTS:
        for w in ROLLING_WINDOWS:
            roll = data[p].rolling(w,min_periods=w)
            add(f'{p}_roll_{w}h_mean',roll.mean())
            add(f'{p}_roll_{w}h_std',roll.std())
    for p in POLLUTANTS:
        for lag in CHANGE_LAGS:
            add(f'{p}_change_{lag}h',data[p]-data[p].shift(lag))
    for lag in CHANGE_LAGS:
        add(f'aqi_change_{lag}h',data['aqi']-data['aqi'].shift(lag))
    for p in POLLUTANTS:
        for w in TREND_WINDOWS:
            add(f'{p}_trend_{w}h',data[p].diff(w)/w)
    for w in TREND_WINDOWS:
        add(f'aqi_trend_{w}h',data['aqi'].diff(w)/w)
    for p in POLLUTANTS:
        add(f'{p}_acceleration',data[p].diff(1)-data[p].diff(3)/3)
    add('aqi_acceleration',data['aqi'].diff(1)-data['aqi'].diff(3)/3)
    add('pm25_pm10_ratio',data['pm25']/data['pm10'].replace(0,np.nan))
    add('pm25_dominance',data['pm25']/(data['pm25']+data['pm10']+1e-6))
    t=data['timestamp'].dt
    for name,x,period in [('hour',t.hour,24),('day',t.dayofweek,7),('year',t.dayofyear,365.25)]:
        add(f'sin_{name}',np.sin(2*np.pi*x/period))
        add(f'cos_{name}',np.cos(2*np.pi*x/period))
    data[features]=data[features].replace([np.inf,-np.inf],np.nan)
    print('Feature count:',len(features))
    return data,features
