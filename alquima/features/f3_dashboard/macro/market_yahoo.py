"""Yahoo Finance market data: US10Y, DXY, BTC, MSTR, STRC."""
import logging

import pandas as pd

from alquima import config
from alquima.common.timeutil import now_utc

log = logging.getLogger("alquima.market")


def collect_market():
    import yfinance as yf
    rows = []
    for name, ticker in config.YF_TICKERS.items():
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
