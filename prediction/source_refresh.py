"""Call the existing collector; credentials never leave the server-side request."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .features import DataUnavailable

REFRESH_URL = 'https://mandalay-aqi-dashboard-bk49.onrender.com/api/refresh'

class SourceRefreshError(DataUnavailable):
    """Only fixed, credential-free diagnostics may be sent to the browser."""
    REASONS = {
        'dashboard_token_missing': (503, 'Manual refresh is not configured. Set DASHBOARD_REFRESH_TOKEN on the Prediction server.'),
        'dashboard_authorization_failed': (503, 'Dashboard refresh authorization failed. Check the Prediction server token configuration.'),
        'dashboard_timeout': (504, 'Dashboard refresh timed out. The previous prediction is retained; try again later.'),
        'dashboard_unavailable': (502, 'Dashboard refresh is unavailable. The previous prediction is retained.'),
        'dashboard_not_completed': (502, 'Dashboard refresh has not completed synchronously. The previous prediction is retained.'),
        'dashboard_invalid_response': (502, 'Dashboard refresh returned an invalid response. The previous prediction is retained.'),
    }

    def __init__(self, code):
        self.code = code
        self.http_status, message = self.REASONS[code]
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirect destination.
        return None


def refresh_source():
    token = os.getenv('DASHBOARD_REFRESH_TOKEN')
    if not token:
        raise SourceRefreshError('dashboard_token_missing')
    request = Request(REFRESH_URL, method='POST', headers={
        'Authorization': 'Bearer ' + token, 'Accept': 'application/json'}, data=b'')
    try:
        with build_opener(NoRedirect()).open(request, timeout=85) as response:
            # A 202 is not completion: do not reread the database prematurely.
            if response.status != 200:
                raise SourceRefreshError('dashboard_not_completed')
            body = response.read(4097)
            if len(body) > 4096:
                raise SourceRefreshError('dashboard_invalid_response')
            result = json.loads(body)
            if (not isinstance(result, dict) or result.get('status') != 'ok'
                    or type(result.get('imported')) is not int or result['imported'] < 0):
                raise SourceRefreshError('dashboard_invalid_response')
    except SourceRefreshError:
        raise
    except HTTPError as exc:
        raise SourceRefreshError('dashboard_authorization_failed' if exc.code in (401, 403) else 'dashboard_unavailable') from exc
    except URLError as exc:
        raise SourceRefreshError('dashboard_timeout' if isinstance(exc.reason, TimeoutError) else 'dashboard_unavailable') from exc
    except TimeoutError as exc:
        raise SourceRefreshError('dashboard_timeout') from exc
    except ValueError as exc:
        raise SourceRefreshError('dashboard_invalid_response') from exc
    except OSError as exc:
        # Do not expose upstream bodies, request headers, or connection details.
        raise SourceRefreshError('dashboard_unavailable') from exc
