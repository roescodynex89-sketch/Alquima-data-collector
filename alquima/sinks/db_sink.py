"""Neon/PostgreSQL sink: appends rows to macro_indicators / market_prices.
Re-running the same collected_at is a no-op (ON CONFLICT DO NOTHING)."""
import logging
import math

from alquima import db

log = logging.getLogger("alquima.sink.db")

INDICATOR_COLS = [
    "indicator", "card", "series_id", "unit", "actual", "actual_date", "previous", "forecast",
    "forecast_source", "forecast_confidence", "forecast_event_date", "forecast_next",
    "next_release", "collected_at", "avg_last_3m", "min_prev_12m", "sahm_gap", "sahm_trigger",
    "dgs2", "dff", "dgs2_minus_dff", "cut_prob_gt_60", "hike_prob_gt_50", "fed_expectation",
    "chg_4w", "chg_prev_4w", "qe_qt_status", "yoy_pct", "chg_3m_pct",
]
MARKET_COLS = [
    "name", "ticker", "last", "last_date", "prev_close", "chg_1d", "chg_1d_pct",
    "chg_1w", "chg_1w_pct", "trend_1w", "collected_at",
]
TABLES = {
    "indicators": ("macro_indicators", INDICATOR_COLS, ("indicator", "collected_at")),
    "market": ("market_prices", MARKET_COLS, ("name", "collected_at")),
}
RETENTION_DAYS = {"market_prices": 90}


def build_insert(name):
    table, cols, keys = TABLES[name]
    return (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
            f"ON CONFLICT ({', '.join(keys)}) DO NOTHING")


def clean(v):
    """numpy/NaN -> plain python / None."""
    if hasattr(v, "item"):
        v = v.item()
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v


def to_rows(name, df):
    cols = TABLES[name][1]
    return [tuple(clean(rec.get(c)) for c in cols) for rec in df.to_dict("records")]


def write(df, name):
    if name not in TABLES:
        raise ValueError(f"unknown dataset: {name}")
    if df is None or df.empty:
        log.warning("%s: nothing to write", name)
        return 0
    table = TABLES[name][0]
    rows = to_rows(name, df)
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(build_insert(name), rows)
            if table in RETENTION_DAYS:
                cur.execute(f"DELETE FROM {table} WHERE collected_at < now() - make_interval(days => %s)",
                            (RETENTION_DAYS[table],))
    log.info("%s: %d rows -> %s", name, len(rows), table)
    return len(rows)