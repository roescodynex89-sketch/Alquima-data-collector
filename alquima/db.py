"""Neon/PostgreSQL helpers.

    python -m alquima.db --init      # create/update tables from sql/schema.sql
    python -m alquima.db --ping      # test the connection
"""
import argparse
import logging
import os
import sys

from alquima import config

log = logging.getLogger("alquima.db")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def connect():
    import psycopg
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(config.DATABASE_URL)


def init_schema():
    with open(os.path.join(ROOT, "sql", "schema.sql"), encoding="utf-8") as f:
        sql = f.read()
    with connect() as conn:
        conn.execute(sql)
    log.info("schema applied")


# ---- ForexFactory cache (used by forecast_ff when DATABASE_URL is set)
def load_ff_cache():
    with connect() as conn:
        cur = conn.execute(
            "SELECT title, country, event_date, impact, forecast, previous, actual "
            "FROM ff_events_cache WHERE event_date > now() - make_interval(days => %s)",
            (config.FF_CACHE_DAYS,))
        return [{"title": t, "country": c, "date": d.isoformat(), "impact": i,
                 "forecast": f, "previous": p, "actual": a}
                for t, c, d, i, f, p, a in cur.fetchall()]


def save_ff_cache(events):
    sql = ("INSERT INTO ff_events_cache (title, event_date, country, impact, forecast, previous, actual) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s) "
           "ON CONFLICT (title, event_date) DO UPDATE SET "
           "country = EXCLUDED.country, impact = EXCLUDED.impact, "
           "forecast = COALESCE(NULLIF(EXCLUDED.forecast, ''), ff_events_cache.forecast), "
           "previous = EXCLUDED.previous, actual = EXCLUDED.actual, updated_at = now()")
    rows = [(e.get("title"), e.get("date"), e.get("country"), e.get("impact"),
             e.get("forecast"), e.get("previous"), e.get("actual")) for e in events]
    with connect() as conn:
        with conn.cursor() as cur:
            if rows:
                cur.executemany(sql, rows)
            cur.execute("DELETE FROM ff_events_cache WHERE event_date < now() - make_interval(days => %s)",
                        (config.FF_CACHE_DAYS,))


def log_run(job, status, rows_written=0, error=None):
    with connect() as conn:
        conn.execute("INSERT INTO collector_runs (job, status, rows_written, error) VALUES (%s, %s, %s, %s)",
                     (job, status, rows_written, error))


if __name__ == "__main__":
    from alquima.common import logger
    logger.setup()
    p = argparse.ArgumentParser()
    p.add_argument("--init", action="store_true")
    p.add_argument("--ping", action="store_true")
    a = p.parse_args()
    if a.init:
        init_schema()
    elif a.ping:
        with connect() as c:
            print(c.execute("SELECT now()").fetchone()[0])
    else:
        p.print_help()
        sys.exit(1)