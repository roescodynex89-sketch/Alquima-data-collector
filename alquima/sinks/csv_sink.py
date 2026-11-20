import logging
import os

from alquima import config

log = logging.getLogger("alquima.sink.csv")


def write(df, name):
    """Write a DataFrame to OUT_DIR/<name>.csv and return the path."""
    path = os.path.join(config.OUT_DIR, f"{name}.csv")
    df.to_csv(path, index=False)
    log.info("%s.csv -> %d rows", name, len(df))
    return path
