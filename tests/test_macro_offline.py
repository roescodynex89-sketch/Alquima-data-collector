"""Offline smoke test: mocks FRED, ForexFactory and Yahoo. Run from repo root:
    OUT_DIR=/tmp/alq_test python tests/test_macro_offline.py
"""
import os
import sys
import types
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("OUT_DIR", os.path.join(ROOT, "output", "_test"))
os.environ["FRED_API_KEY"] = "dummy"

import pandas as pd

from alquima.common import http
from alquima.common.timeutil import now_utc
from alquima.features.f3_dashboard.macro import fred, run

now = now_utc()
iso = lambda dt: dt.isoformat(timespec="seconds")

EVENTS = [
    {"title": "CPI y/y", "country": "USD", "date": iso(now - timedelta(days=10)), "forecast": "4.1%"},
    {"title": "CPI y/y", "country": "USD", "date": iso(now + timedelta(days=20)), "forecast": "4.2%"},
    {"title": "Core PCE Price Index m/m", "country": "USD", "date": iso(now - timedelta(days=3)), "forecast": "0.3%"},
    {"title": "Unemployment Rate", "country": "EUR", "date": iso(now - timedelta(days=3)), "forecast": "6.0%"},
]


class R:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def raise_for_status(self):
        if self.status_code >= 400:
            e = http.requests.HTTPError("http %s" % self.status_code)
            e.response = self
            raise e

    def json(self):
        return self._d


http.get = lambda url, **kw: R(200, EVENTS) if "thisweek" in url else R(404, None)

BASE = {"CPIAUCSL": 300, "PCEPILFE": 125, "PAYEMS": 159000, "UNRATE": 4.1,
        "FEDFUNDS": 3.88, "DGS2": 4.8, "DFF": 4.0, "WALCL": 6.7e6, "M2SL": 23000}
GROWTH = ("CPIAUCSL", "PCEPILFE", "PAYEMS", "WALCL", "M2SL")


def fake_series(sid, limit=40):
    return [(f"2025-{(i % 12) + 1:02d}-01", BASE[sid] * (1 + 0.003 * i if sid in GROWTH else 1))
            for i in range(limit)]


fred.fred_series = fake_series
today = now.date()
fred.fred_release_dates = lambda rid: [today.isoformat(), (today + timedelta(days=7)).isoformat()]

# fake yfinance
class FakeTicker:
    def __init__(self, t):
        pass

    def history(self, period, interval):
        idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=20)
        return pd.DataFrame({"Close": [100 + i for i in range(20)]}, index=idx)


sys.modules["yfinance"] = types.SimpleNamespace(Ticker=FakeTicker)

out = os.environ["OUT_DIR"]
for f in ("indicators.csv", "market.csv", "ff_cache.json"):
    p = os.path.join(out, f)
    if os.path.exists(p):
        os.remove(p)

assert run.main(["--sink", "csv"]) == 0
ind = pd.read_csv(os.path.join(out, "indicators.csv")).set_index("indicator")
mkt = pd.read_csv(os.path.join(out, "market.csv")).set_index("name")

assert len(ind) == 7 and len(mkt) == 5
assert ind.loc["CPI", "forecast_source"] == "forexfactory" and ind.loc["CPI", "forecast"] == 4.1
assert ind.loc["CPI", "forecast_confidence"] == "high" and ind.loc["CPI", "forecast_next"] == 4.2
assert ind.loc["CORE_PCE", "forecast_confidence"] == "low"
assert ind.loc["UNRATE", "forecast_confidence"] == "low"
assert bool(ind.loc["FEDFUNDS", "hike_prob_gt_50"]) and ind.loc["FEDFUNDS", "fed_expectation"] == "HIKE"
assert ind.loc["BALANCE_SHEET", "countdown"] != "released"
assert mkt.loc["BTC", "trend_1w"] == "rising"

# --part and --sink db behaviour
assert run.main(["--sink", "csv", "--part", "market"]) == 0
assert run.main(["--sink", "db", "--part", "market"]) == 1
print("ALL_TESTS_OK")
