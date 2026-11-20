"""FRED API helpers + release calendar."""
from datetime import date, timedelta

from alquima import config
from alquima.common import http
from alquima.common.timeutil import now_utc, ny_to_utc, NY

_REL_CACHE = {}


def fred_series(series_id, limit=40):
    """Latest observations, oldest -> newest, as list of (date, float)."""
    r = http.get(f"{config.FRED_BASE}/series/observations", params={
        "series_id": series_id, "api_key": config.FRED_KEY, "file_type": "json",
        "sort_order": "desc", "limit": limit})
    r.raise_for_status()
    obs = [(o["date"], float(o["value"])) for o in r.json()["observations"] if o["value"] != "."]
    return list(reversed(obs))


def fred_release_dates(release_id):
    """Sorted list of release dates (YYYY-MM-DD) from yesterday onward."""
    if release_id in _REL_CACHE:
        return _REL_CACHE[release_id]
    r = http.get(f"{config.FRED_BASE}/release/dates", params={
        "release_id": release_id, "api_key": config.FRED_KEY, "file_type": "json",
        "include_release_dates_with_no_data": "true", "sort_order": "desc", "limit": 20})
    r.raise_for_status()
    cutoff = (now_utc().date() - timedelta(days=1)).isoformat()
    dates = sorted(d["date"] for d in r.json().get("release_dates", []) if d["date"] >= cutoff)
    _REL_CACHE[release_id] = dates
    return dates


def pick_next(indicator, dates):
    """First release date whose release TIME is still in the future -> aware UTC datetime."""
    hh, mm = config.RELEASE_TIME_NY.get(indicator, (8, 30))
    now = now_utc()
    for d in dates:
        dt = ny_to_utc(date.fromisoformat(d), hh, mm)
        if dt > now:
            return dt
    return None


def next_walcl_release():
    """Fallback: next Thursday 4:30pm New York (H.4.1 weekly release)."""
    now = now_utc()
    start = now.astimezone(NY).date() if NY is not None else now.date()
    for i in range(0, 8):
        cand = start + timedelta(days=i)
        if cand.weekday() == 3:
            dt = ny_to_utc(cand, 16, 30)
            if dt > now:
                return dt
    return None


def yoy_series(obs):
    """Index series -> YoY % series."""
    return [(obs[i][0], (obs[i][1] / obs[i - 12][1] - 1) * 100) for i in range(12, len(obs))]


def mom_diff_series(obs):
    """Level series -> month-over-month change (NFP in thousands)."""
    return [(obs[i][0], obs[i][1] - obs[i - 1][1]) for i in range(1, len(obs))]
