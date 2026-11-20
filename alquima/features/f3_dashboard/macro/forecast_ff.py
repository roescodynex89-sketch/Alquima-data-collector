"""ForexFactory forecast feed + cache (DB table when DATABASE_URL is set, else local JSON file)."""
import json
import logging
from datetime import datetime, timedelta, timezone

import requests

from alquima import config
from alquima.common import http
from alquima.common.timeutil import now_utc

log = logging.getLogger("alquima.ff")


def ev_dt(e):
    dt = datetime.fromisoformat(e["date"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_cache():
    """DB table when DATABASE_URL is set (GitHub Actions), else a local JSON file."""
    if config.DATABASE_URL:
        try:
            from alquima import db
            return db.load_ff_cache()
        except Exception as e:
            log.warning("ff cache: DB load failed, starting empty: %s", e)
            return []
    try:
        with open(config.FF_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_cache(events):
    if config.DATABASE_URL:
        try:
            from alquima import db
            db.save_ff_cache(events)
        except Exception as e:
            log.warning("ff cache: DB save failed: %s", e)
        return
    try:
        with open(config.FF_CACHE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False)
    except Exception as ex:
        log.warning("could not write ff cache: %s", ex)


def fetch_ff_events():
    """This week + next week USD events, merged into a cache so a forecast seen
    before a release is still available after the weekly feed rolls over."""
    fresh = []
    for url in config.FF_URLS:
        try:
            r = http.get(url, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            fresh += r.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                log.info("ForexFactory feed not published yet (404): %s", url)
            else:
                log.warning("ForexFactory feed failed (%s): %s", url, e)
        except Exception as e:
            log.warning("ForexFactory feed failed (%s): %s", url, e)

    merged = {(e.get("title"), e.get("date")): e for e in load_cache()}
    if not fresh and not merged:
        log.warning("ForexFactory: no live feed and empty cache -> all forecasts will be fallback")
    new_count = 0
    for e in fresh:
        if e.get("country") != "USD":
            continue
        key = (e.get("title"), e.get("date"))
        old = merged.get(key, {})
        new = {k: e.get(k) for k in config.FF_FIELDS}
        if not new.get("forecast") and old.get("forecast"):
            new["forecast"] = old["forecast"]   # never lose a forecast we already saw
        merged[key] = new
        new_count += 1

    cutoff = now_utc() - timedelta(days=config.FF_CACHE_DAYS)
    events = []
    for e in merged.values():
        try:
            if ev_dt(e) >= cutoff:
                events.append(e)
        except Exception:
            continue
    save_cache(events)
    log.info("ForexFactory USD events: %d fresh, %d in cache", new_count, len(events))
    return events


def parse_num(s):
    """'2.9%' -> 2.9 ; '180K' -> 180 ; '' -> None"""
    if not s:
        return None
    s = str(s).replace("%", "").replace(",", "").strip()
    mult = 1.0
    if s.endswith("K"):
        s = s[:-1]
    elif s.endswith("M"):
        s, mult = s[:-1], 1000.0
    try:
        return float(s) * mult
    except ValueError:
        return None


def find_ff(events, key):
    """-> (latest_event, next_event).
    latest_event: most recent already-happened event (<= LATEST_MAX_AGE_DAYS old);
                  its forecast belongs to the latest actual.
    next_event:   soonest upcoming event; its forecast belongs to the next release."""
    names = [t.lower() for t in config.FF_MAP[key]]
    now = now_utc()
    past, future = [], []
    for e in events:
        if (e.get("title") or "").lower() not in names:
            continue
        try:
            dt = ev_dt(e)
        except Exception:
            continue
        (future if dt >= now else past).append((dt, e))
    latest = None
    if past:
        dt, e = max(past, key=lambda x: x[0])
        if (now - dt).days <= config.LATEST_MAX_AGE_DAYS:
            latest = e
    nxt = min(future, key=lambda x: x[0])[1] if future else None
    return latest, nxt