"""Call the existing collector; credentials never leave the server-side request."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .features import DataUnavailable

REFRESH_URL = 'https://mandalay-aqi-dashboard-bk49.onrender.com/api/refresh'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirect destination.
        return None


def refresh_source():
    token = os.getenv('DASHBOARD_REFRESH_TOKEN')
    if not token:
        raise DataUnavailable('Manual refresh is not configured on the Prediction server')
    request = Request(REFRESH_URL, method='POST', headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}, data=b'')
    try:
        with build_opener(NoRedirect()).open(request, timeout=85) as response:
            # A 202 is not completion: do not reread the database prematurely.
            if response.status != 200:
                raise DataUnavailable('Dashboard source refresh did not complete synchronously')
            body = response.read(4097)
            if len(body) > 4096:
                raise DataUnavailable('Dashboard source refresh returned an invalid response')
            result = json.loads(body)
            if (not isinstance(result, dict) or result.get('status') != 'ok'
                    or type(result.get('imported')) is not int or result['imported'] < 0):
                raise DataUnavailable('Dashboard source refresh returned an invalid response')
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        # Do not expose upstream bodies, request headers, or connection details.
        raise DataUnavailable('Dashboard source refresh failed; try again later') from exc
