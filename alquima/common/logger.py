import logging
import os
import sys

from alquima import config

_done = False


def setup(logfile="collector.log"):
    """Console + file logging. Safe to call more than once."""
    global _done
    log = logging.getLogger("alquima")
    if _done:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(os.path.join(config.OUT_DIR, logfile), encoding="utf-8"),
              logging.StreamHandler(sys.stdout)):
        h.setFormatter(fmt)
        log.addHandler(h)
    _done = True
    return log
