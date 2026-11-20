"""Entry point for Card 1-3 data.

    python -m alquima.features.f3_dashboard.macro.run --sink csv
    python -m alquima.features.f3_dashboard.macro.run --sink db --part market
    python -m alquima.features.f3_dashboard.macro.run --sink both --part indicators
"""
import argparse
import sys

from alquima import config
from alquima.common import logger

EXPECTED_ROWS = {"indicators": 7, "market": 5}


def main(argv=None):
    p = argparse.ArgumentParser(description="Alquima Card 1-3 data collector")
    p.add_argument("--sink", choices=["csv", "db", "both"], default="csv")
    p.add_argument("--part", choices=["all", "market", "indicators"], default="all")
    args = p.parse_args(argv)

    log = logger.setup()

    if args.part in ("all", "indicators") and not config.FRED_KEY:
        log.error("FRED_API_KEY not set. Get a free key at fred.stlouisfed.org and set it.")
        return 1
    use_db = args.sink in ("db", "both")
    if use_db and not config.DATABASE_URL:
        log.error("DATABASE_URL not set (needed for --sink %s).", args.sink)
        return 1

    from alquima.sinks import csv_sink, db_sink
    sinks = {"csv": [csv_sink], "db": [db_sink], "both": [csv_sink, db_sink]}[args.sink]

    results = {}
    if args.part in ("all", "indicators"):
        from .indicators import collect_indicators
        results["indicators"] = collect_indicators()
    if args.part in ("all", "market"):
        from .market_yahoo import collect_market
        results["market"] = collect_market()

    written, error, code = 0, None, 0
    for name, df in results.items():
        for s in sinks:
            try:
                n = s.write(df, name)
                if s is db_sink:
                    written += n or 0
            except Exception as e:
                log.error("%s sink failed for %s: %s", s.__name__.split(".")[-1], name, e)
                error, code = f"{name}: {e}", 2
        print(f"\n=== {name} ===")
        print(df.to_string(index=False))

    if use_db:
        complete = all(len(df) >= EXPECTED_ROWS[n] for n, df in results.items())
        status = "error" if code else ("ok" if complete else "partial")
        try:
            from alquima import db
            db.log_run(f"macro:{args.part}", status, written, error)
        except Exception as e:
            log.warning("could not log run: %s", e)
    return code


if __name__ == "__main__":
    sys.exit(main())