"""Card 1 (CPI, Core PCE, NFP, UNRATE), Card 2 (Fed rate, QE/QT), M2 (Card 3).
Raw + derived fields only. Bullish/Bearish scoring lives in Express."""
import logging
from datetime import date

import pandas as pd

from alquima import config
from alquima.common.timeutil import now_utc, ny_to_utc, countdown
from . import fred, forecast_ff

log = logging.getLogger("alquima.indicators")


def collect_indicators():
    rows = []
    ff = forecast_ff.fetch_ff_events()

    def add(indicator, card, series_id, series, unit, extra=None, next_dt=None):
        actual_d, actual = series[-1]
        prev = series[-2][1] if len(series) > 1 else None

        if indicator in config.FF_MAP:
            latest_ev, next_ev = forecast_ff.find_ff(ff, indicator)
        else:
            latest_ev, next_ev = None, None
        fc_latest = forecast_ff.parse_num(latest_ev.get("forecast")) if latest_ev else None
        fc_next = forecast_ff.parse_num(next_ev.get("forecast")) if next_ev else None

        if fc_latest is not None:
            fc, fc_src, fc_conf = fc_latest, "forexfactory", "high"
        else:
            fc, fc_src, fc_conf = prev, "fallback_previous_actual", "low"

        if next_dt is None and next_ev:
            next_dt = forecast_ff.ev_dt(next_ev)
        if next_dt is None and indicator in config.RELEASE_IDS:
            try:
                next_dt = fred.pick_next(indicator, fred.fred_release_dates(config.RELEASE_IDS[indicator]))
            except Exception as e:
                log.warning("next release failed for %s: %s", indicator, e)
        if next_dt is None and indicator == "BALANCE_SHEET":
            next_dt = fred.next_walcl_release()

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
        add("CPI", 1, "CPIAUCSL", fred.yoy_series(fred.fred_series("CPIAUCSL", 30)), "% YoY")

    @job
    def core_pce():
        add("CORE_PCE", 1, "PCEPILFE", fred.yoy_series(fred.fred_series("PCEPILFE", 30)), "% YoY")

    @job
    def nfp():
        s = fred.mom_diff_series(fred.fred_series("PAYEMS", 15))  # thousands
        add("NFP", 1, "PAYEMS", s, "K jobs",
            {"avg_last_3m": round(sum(v for _, v in s[-3:]) / 3, 1)})

    @job
    def unrate():
        s = fred.fred_series("UNRATE", 14)
        min12 = min(v for _, v in s[-13:-1])  # 12 months before latest
        add("UNRATE", 1, "UNRATE", s, "%",
            {"min_prev_12m": round(min12, 2),
             "sahm_gap": round(s[-1][1] - min12, 2),
             "sahm_trigger": (s[-1][1] - min12) >= 0.5})

    @job
    def fedfunds():
        s = fred.fred_series("FEDFUNDS", 6)            # monthly average (lags after a rate move)
        dgs2 = fred.fred_series("DGS2", 10)[-1][1]
        try:
            dff = fred.fred_series("DFF", 10)[-1][1]   # daily effective rate = current policy level
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
        nxt = next((d for d in config.FOMC_DECISION_DATES
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
        s = fred.fred_series("WALCL", 20)  # weekly, millions USD
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
        raw = fred.fred_series("M2SL", 30)  # monthly, billions
        yoy = fred.yoy_series(raw)
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
