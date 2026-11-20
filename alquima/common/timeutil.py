from datetime import datetime, timedelta, timezone

try:  # needs the `tzdata` package on Windows (in requirements.txt)
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # fallback: assume EST (UTC-5)
    NY = None


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
