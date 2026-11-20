"""One shared HTTP session with retries on 429/5xx. Callers still do r.raise_for_status()."""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_session = None


def _get_session():
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), raise_on_status=False)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def get(url, params=None, headers=None, timeout=30):
    return _get_session().get(url, params=params, headers=headers, timeout=timeout)

def post(url, params=None, headers=None, json=None, timeout=60):
    """No automatic retry for POST; callers handle their own retries."""
    return _get_session().post(
        url,
        params=params,
        headers=headers,
        json=json,
        timeout=timeout,
    )