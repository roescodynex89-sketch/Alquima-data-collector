"""
Alquima Roes - Step 1: data collection -> CSV (no DB yet).

Run:
    pip install -r requirements.txt
    set FRED_API_KEY=your_key        (Windows)   /   export FRED_API_KEY=your_key  (Linux/Mac)
    python collector.py

Output (./output):
    indicators.csv   - Card 1 + Card 2 + M2 (FRED data, forecast, next release, countdown)
    market.csv       - Card 3 market data + BTC/MSTR/STRC (Yahoo Finance)
    collector.log    - errors / warnings per source
    ff_cache.json    - ForexFactory events seen so far (so forecasts survive week rollover)

Forecast columns in indicators.csv:
    forecast             forecast for the LATEST actual (use this for Actual vs Forecast scoring)
    forecast_source      forexfactory | fallback_previous_actual
    forecast_confidence  high | low   (low = fallback, do NOT give Strong Bullish/Bearish on it)
    forecast_next        forecast for the NEXT release (display only)

Scoring (Bullish/Bearish logic) is NOT here yet. Check the CSVs first.
"""
import os
import sys
import json
import logging
from datetime import datetime, date, timedelta, timezone

import requests
import pandas as pd

try:  # needs `tzdata` package on Windows (in requirements.txt)
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # fallback: assume EST (UTC-5)
    NY = None

OUT_DIR = "output"
FRED_KEY = os.getenv("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred"
FF_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
FF_CACHE = os.path.join(OUT_DIR, "ff_cache.json")
FF_CACHE_DAYS = 90          # keep seen events this long
LATEST_MAX_AGE_DAYS = 45    # a past event older than this is not "the latest release"
FF_FIELDS = ("title", "country", "date", "impact", "forecast", "previous", "actual")

# 2026 FOMC decision days (second day of each meeting, 2:00pm ET). Verify on federalreserve.gov.
FOMC_DECISION_DATES = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# FRED release ids used only for next-release dates (countdown)
RELEASE_IDS = {"CPI": 10, "NFP": 50, "UNRATE": 50, "CORE_PCE": 54, "BALANCE_SHEET": 20, "M2": 21}
# Usual release time (New York wall clock) when we only know the date
RELEASE_TIME_NY = {"CPI": (8, 30), "CORE_PCE": (8, 30), "NFP": (8, 30), "UNRATE": (8, 30),
                   "BALANCE_SHEET": (16, 30), "M2": (16, 30)}

# ForexFactory title -> our indicator (USD only). Core PCE m/m removed on purpose:
# its forecast is a monthly %, which would not match our YoY actual.
FF_MAP = {
    "CPI": ["CPI y/y"],
    "CORE_PCE": ["Core PCE Price Index y/y"],
    "NFP": ["Non-Farm Employment Change"],
    "UNRATE": ["Unemployment Rate"],
    "FEDFUNDS": ["Federal Funds Rate"],
}

YF_TICKERS = {
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "BTC": "BTC-USD",
    "MSTR": "MSTR",
    "STRC": "STRC",
}

os.makedirs(OUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(os.path.join(OUT_DIR, "collector.log"), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("collector")


# ---------------------------------------------------------------- time helpers
def now_utc():
    return datetime.now(timezone.utc)


def ny_to_utc(d, hh, mm):
    """date + New York wall time -> aware UTC datetime."""
    if NY is not None:
        return datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).astimezone(timezone.utc)
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=timezone.utc) + timedelta(hours=5)


def countdown(dt):
    if dt is None:
        return None
    secs = (dt - now_utc()).total_seconds()
    if secs <= 0:
        return "released"
    return f"{int(secs // 86400)}d {int(secs % 86400 // 3600)}h"


# ---------------------------------------------------------------- FRED
def fred_series(series_id, limit=40):
    """Latest observations, oldest -> newest, as list of (date, float)."""
    r = requests.get(f"{FRED_BASE}/series/observations", params={
        "series_id": series_id, "api_key": FRED_KEY, "file_type": "json",
        "sort_order": "desc", "limit": limit}, timeout=30)
    r.raise_for_status()
    obs = [(o["date"], float(o["value"])) for o in r.json()["observations"] if o["value"] != "."]
    return list(reversed(obs))


_REL_CACHE = {}


def fred_release_dates(release_id):
    """Sorted list of release dates (YYYY-MM-DD) from yesterday onward."""
    if release_id in _REL_CACHE:
        return _REL_CACHE[release_id]
    r = requests.get(f"{FRED_BASE}/release/dates", params={
        "release_id": release_id, "api_key": FRED_KEY, "file_type": "json",
        "include_release_dates_with_no_data": "true", "sort_order": "desc", "limit": 20},
        timeout=30)
    r.raise_for_status()
    cutoff = (now_utc().date() - timedelta(days=1)).isoformat()
    dates = sorted(d["date"] for d in r.json().get("release_dates", []) if d["date"] >= cutoff)
    _REL_CACHE[release_id] = dates
    return dates


def pick_next(indicator, dates):
    """First release date whose release TIME is still in the future -> aware UTC datetime."""
    hh, mm = RELEASE_TIME_NY.get(indicator, (8, 30))
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


# ---------------------------------------------------------------- Forecast (ForexFactory feed + cache)
def ev_dt(e):
    dt = datetime.fromisoformat(e["date"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_ff_cache():
    try:
        with open(FF_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def fetch_ff_events():
    """This week + next week USD events, merged into a local cache so a forecast
    seen before a release is still available after the weekly feed rolls over."""
    fresh = []
    for url in FF_URLS:
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            fresh += r.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                log.info("ForexFactory feed not published yet (404): %s", url)
            else:
                log.warning("ForexFactory feed failed (%s): %s", url, e)
        except Exception as e:
            log.warning("ForexFactory feed failed (%s): %s", url, e)

    merged = {(e.get("title"), e.get("date")): e for e in load_ff_cache()}
    new_count = 0
    for e in fresh:
        if e.get("country") != "USD":
            continue
        key = (e.get("title"), e.get("date"))
        old = merged.get(key, {})
        new = {k: e.get(k) for k in FF_FIELDS}
        if not new.get("forecast") and old.get("forecast"):
            new["forecast"] = old["forecast"]   # never lose a forecast we already saw
        merged[key] = new
        new_count += 1

    cutoff = now_utc() - timedelta(days=FF_CACHE_DAYS)
    events = []
    for e in merged.values():
        try:
            if ev_dt(e) >= cutoff:
                events.append(e)
        except Exception:
            continue
    try:
        with open(FF_CACHE, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False)
    except Exception as ex:
        log.warning("could not write ff cache: %s", ex)
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
    names = [t.lower() for t in FF_MAP[key]]
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
        if (now - dt).days <= LATEST_MAX_AGE_DAYS:
            latest = e
    nxt = min(future, key=lambda x: x[0])[1] if future else None
    return latest, nxt


# ---------------------------------------------------------------- Collect: indicators
def collect_indicators():
    rows = []
    ff = fetch_ff_events()

    def add(indicator, card, series_id, series, unit, extra=None, next_dt=None):
        actual_d, actual = series[-1]
        prev = series[-2][1] if len(series) > 1 else None

        latest_ev, next_ev = find_ff(ff, indicator) if indicator in FF_MAP else (None, None)
        fc_latest = parse_num(latest_ev.get("forecast")) if latest_ev else None
        fc_next = parse_num(next_ev.get("forecast")) if next_ev else None

        if fc_latest is not None:
            fc, fc_src, fc_conf = fc_latest, "forexfactory", "high"
        else:
            fc, fc_src, fc_conf = prev, "fallback_previous_actual", "low"

        if next_dt is None and next_ev:
            next_dt = ev_dt(next_ev)
        if next_dt is None and indicator in RELEASE_IDS:
            try:
                next_dt = pick_next(indicator, fred_release_dates(RELEASE_IDS[indicator]))
            except Exception as e:
                log.warning("next release failed for %s: %s", indicator, e)
        if next_dt is None and indicator == "BALANCE_SHEET":
            next_dt = next_walcl_release()

        row = {
            "indicator": indicator, "card": card, "series_id": series_id, "unit": unit,
            "actual": round(actual, 4), "actual_date": actual_d,
            "previous": None if prev is None else round(prev, 4),
            "forecast": None if fc is None else round(fc, 4),
            "forecast_source": fc_src, "forecast_confidence": fc_conf,
            "forecast_event_date": latest_ev["date"] if latest_ev else None,
            "forecast_next": None if fc_next is None else round(fc_next, 4),
            "next_release": next_dt.isoformat(timespec="seconds") if next_dt else None,
            "countdown": countdown(next_dt),
            "collected_at": now_utc().isoformat(timespec="seconds"),
        }
        row.update(extra or {})
        rows.append(row)

    jobs = []

    def job(fn):
        jobs.append(fn)
        return fn

    @job
    def cpi():
        add("CPI", 1, "CPIAUCSL", yoy_series(fred_series("CPIAUCSL", 30)), "% YoY")

    @job
    def core_pce():
        add("CORE_PCE", 1, "PCEPILFE", yoy_series(fred_series("PCEPILFE", 30)), "% YoY")

    @job
    def nfp():
        s = mom_diff_series(fred_series("PAYEMS", 15))  # thousands
        add("NFP", 1, "PAYEMS", s, "K jobs",
            {"avg_last_3m": round(sum(v for _, v in s[-3:]) / 3, 1)})

    @job
    def unrate():
        s = fred_series("UNRATE", 14)
        min12 = min(v for _, v in s[-13:-1])  # 12 months before latest
        add("UNRATE", 1, "UNRATE", s, "%",
            {"min_prev_12m": round(min12, 2),
             "sahm_gap": round(s[-1][1] - min12, 2),
             "sahm_trigger": (s[-1][1] - min12) >= 0.5})

    @job
    def fedfunds():
        s = fred_series("FEDFUNDS", 6)            # monthly average (lags after a rate move)
        dgs2 = fred_series("DGS2", 10)[-1][1]
        try:
            dff = fred_series("DFF", 10)[-1][1]   # daily effective rate = current policy level
        except Exception as e:
            log.warning("DFF failed, using monthly FEDFUNDS for spread: %s", e)
            dff = s[-1][1]
        spread = dgs2 - dff
        if spread <= -0.25:
            expectation = "CUT"
        elif spread >= 0.25:
            expectation = "HIKE"
        else:
            expectation = "HOLD"
        nxt = next((d for d in FOMC_DECISION_DATES
                    if ny_to_utc(date.fromisoformat(d), 14, 0) > now_utc()), None)
        next_dt = ny_to_utc(date.fromisoformat(nxt), 14, 0) if nxt else None
        # proxies only, NOT real CME FedWatch probabilities
        add("FEDFUNDS", 2, "FEDFUNDS", s, "%", {
            "dgs2": round(dgs2, 3), "dff": round(dff, 3),
            "dgs2_minus_dff": round(spread, 3),
            "cut_prob_gt_60": spread <= -0.25,
            "hike_prob_gt_50": spread >= 0.25,
            "fed_expectation": expectation,
        }, next_dt=next_dt)

    @job
    def balance_sheet():
        s = fred_series("WALCL", 20)  # weekly, millions USD
        now_v, m1 = s[-1][1], s[-5][1]       # ~4 weeks ago
        m2_ = s[-9][1]                        # ~8 weeks ago
        chg_now, chg_prev = now_v - m1, m1 - m2_
        if chg_now > 0:
            status = "QE_STARTED"
        elif chg_now > chg_prev:
            status = "QT_SLOWING"
        else:
            status = "QT_ONGOING"
        add("BALANCE_SHEET", 2, "WALCL", s, "USD mn",
            {"chg_4w": round(chg_now, 0), "chg_prev_4w": round(chg_prev, 0), "qe_qt_status": status})

    @job
    def m2():
        raw = fred_series("M2SL", 30)  # monthly, billions
        yoy = yoy_series(raw)
        three_m = (raw[-1][1] / raw[-4][1] - 1) * 100
        add("M2", 3, "M2SL", raw, "USD bn",
            {"yoy_pct": round(yoy[-1][1], 3), "chg_3m_pct": round(three_m, 3)})

    for fn in jobs:
        try:
            fn()
            log.info("OK   %s", fn.__name__)
        except Exception as e:
            log.error("FAIL %s: %s", fn.__name__, e)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Collect: market (Yahoo)
def collect_market():
    import yfinance as yf
    rows = []
    for name, ticker in YF_TICKERS.items():
        try:
            h = yf.Ticker(ticker).history(period="1mo", interval="1d")["Close"].dropna()
            if len(h) < 6:
                raise ValueError("not enough data")
            last, prev_day, prev_week = h.iloc[-1], h.iloc[-2], h.iloc[-6]
            rows.append({
                "name": name, "ticker": ticker,
                "last": round(float(last), 4), "last_date": str(h.index[-1].date()),
                "prev_close": round(float(prev_day), 4),
                "chg_1d": round(float(last - prev_day), 4),
                "chg_1d_pct": round(float((last / prev_day - 1) * 100), 3),
                "chg_1w": round(float(last - prev_week), 4),
                "chg_1w_pct": round(float((last / prev_week - 1) * 100), 3),
                "trend_1w": "rising" if last > prev_week else "falling",
                "collected_at": now_utc().isoformat(timespec="seconds"),
            })
            log.info("OK   %s (%s)", name, ticker)
        except Exception as e:
            log.error("FAIL %s (%s): %s", name, ticker, e)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- Main
def main():
    if not FRED_KEY:
        log.error("FRED_API_KEY not set. Get a free key at fred.stlouisfed.org and set it.")
        sys.exit(1)

    ind = collect_indicators()
    ind.to_csv(os.path.join(OUT_DIR, "indicators.csv"), index=False)
    log.info("indicators.csv -> %d rows", len(ind))

    mkt = collect_market()
    mkt.to_csv(os.path.join(OUT_DIR, "market.csv"), index=False)
    log.info("market.csv -> %d rows", len(mkt))

    print("\n=== indicators.csv ===")
    print(ind.to_string(index=False))
    print("\n=== market.csv ===")
    print(mkt.to_string(index=False))


if __name__ == "__main__":
    main()
