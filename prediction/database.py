"""Existing dashboard PostgreSQL schema; read-only transactions, no DDL/DML."""
import os
from urllib.parse import urlsplit
import psycopg2
from psycopg2.extras import RealDictCursor
from .features import DataUnavailable, HISTORY_HOURS

QUERY = '''
WITH origin AS (
 SELECT max(timestamp) AS ts FROM mandalay_readings
 WHERE timestamp <= CURRENT_TIMESTAMP AND mod(extract(epoch FROM timestamp),3600)=1800
)
SELECT r.timestamp, r.pm2_5, r.pm10, r.carbon_monoxide,
 r.nitrogen_dioxide, r.sulphur_dioxide, r.ozone, r.source,
 c.cpcb_aqi AS stored_cpcb_aqi, c.calculation_version, c.status AS cpcb_status,
 c.calculated_at
FROM mandalay_readings r CROSS JOIN origin o
LEFT JOIN mandalay_cpcb_aqi c ON c.timestamp=r.timestamp
WHERE r.timestamp BETWEEN o.ts - (%s * INTERVAL '1 hour') AND o.ts
 AND mod(extract(epoch FROM r.timestamp),3600)=1800
ORDER BY r.timestamp
'''

class ObservationStore:
    def __init__(self, url=None):
        self.url = url if url is not None else os.getenv('DATABASE_URL','')

    def fetch(self):
        url = self.url.replace('postgresql+psycopg://','postgresql://',1).replace('postgresql+psycopg2://','postgresql://',1)
        if not url or urlsplit(url).scheme not in ('postgres','postgresql'):
            raise DataUnavailable('DATABASE_URL must be configured for the existing PostgreSQL database')
        try:
            with psycopg2.connect(url, connect_timeout=8, options='-c default_transaction_read_only=on -c statement_timeout=10000') as conn:
                conn.set_session(readonly=True)
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(QUERY,(HISTORY_HOURS-1,))
                    return [dict(row) for row in cur.fetchall()]
        except psycopg2.Error as exc:
            # Never return driver text containing hosts/usernames/credentials.
            raise DataUnavailable('PostgreSQL connection, read access, or dashboard schema unavailable') from exc
