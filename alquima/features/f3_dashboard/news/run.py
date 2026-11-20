"""Entry point for Card 5 (AI market brief, 12-hour slots). Run hourly.

    python -m alquima.features.f3_dashboard.news.run --sink csv     # dry run, nothing written to the DB
    python -m alquima.features.f3_dashboard.news.run --sink db      # real run (Neon)
"""
import argparse
import sys

from alquima import config
from alquima.common import logger
from alquima.common.timeutil import now_utc


def main(argv=None):
    p = argparse.ArgumentParser(description="Alquima Card 5 news collector")
    p.add_argument("--sink", choices=["csv", "db"], default="csv")
    args = p.parse_args(argv)
    log = logger.setup()

    if args.sink == "db" and not config.DATABASE_URL:
        log.error("DATABASE_URL not set (needed for --sink db).")
        return 1

    from . import fetch, slots, llm_summary
    from .store import MemoryStore, DbStore

    now = now_utc()
    items, failed = fetch.fetch_all(now)
    log.info("fetched %d articles, %d feed problems", len(items), len(failed))
    if not items:
        log.error("no articles fetched from any feed")
        return 1

    summarize = None
    if config.GEMINI_API_KEY:
        summarize = llm_summary.summarize
    else:
        log.warning("GEMINI_API_KEY not set: storing raw news only, no summary.")

    store = MemoryStore() if args.sink == "csv" else DbStore()
    code = 0
    try:
        res = slots.process(store, items, now, summarize)
    except Exception as e:
        log.error("news run failed: %s", type(e).__name__)
        code, res = 2, {"stored": 0, "summarized": [], "finalized": [], "llm_errors": [str(e)[:200]]}

    log.info("slot %s | stored %d | summarized %d | finalized %d | llm errors %d",
             slots.slot_start(now).isoformat(), res["stored"], len(res["summarized"]),
             len(res["finalized"]), len(res["llm_errors"]))

    if args.sink == "csv" and code == 0:
        import pandas as pd
        from alquima.sinks import csv_sink
        csv_sink.write(pd.DataFrame(store.raw), "news_raw")
        csv_sink.write(pd.DataFrame(list(store.summaries.values())), "news_slot_summaries")
        for s in store.summaries.values():
            print(f"\n[{s['slot_start']:%Y-%m-%d %H:%M} UTC] {s['sentiment']}")
            for k in ("macro_fed", "crypto_mstr", "law_geopolitics", "btc_impact"):
                print(f"  {k}: {s[k]}")

    if args.sink == "db":
        status = "error" if (code or res["llm_errors"]) else ("partial" if failed else "ok")
        err = "; ".join(res["llm_errors"] + failed)[:500] or None
        try:
            from alquima import db
            db.log_run("news", status, res["stored"], err)
        except Exception as e:
            log.warning("could not log run: %s", type(e).__name__)
        store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())