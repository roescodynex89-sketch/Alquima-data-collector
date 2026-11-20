"""Central settings + constants. Secrets come from environment (.env locally, GitHub Secrets in Actions)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

FRED_KEY = os.getenv("FRED_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
OUT_DIR = os.getenv("OUT_DIR", "output")
os.makedirs(OUT_DIR, exist_ok=True)

FRED_BASE = "https://api.stlouisfed.org/fred"

FF_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
]
FF_CACHE = os.path.join(OUT_DIR, "ff_cache.json")   # moves to a DB table in the DB step
FF_CACHE_DAYS = 90          # keep seen events this long
LATEST_MAX_AGE_DAYS = 45    # a past event older than this is not "the latest release"
FF_FIELDS = ("title", "country", "date", "impact", "forecast", "previous", "actual")

# 2026 FOMC decision days (second day of each meeting, 2:00pm ET). Verify on federalreserve.gov.
FOMC_DECISION_DATES = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]

# FRED release ids used only for next-release dates (countdown)
RELEASE_IDS = {"CPI": 10, "NFP": 50, "UNRATE": 50, "CORE_PCE": 54, "BALANCE_SHEET": 20, "M2": 21}
# Usual release time (New York wall clock) when we only know the date
RELEASE_TIME_NY = {"CPI": (8, 30), "CORE_PCE": (8, 30), "NFP": (8, 30), "UNRATE": (8, 30),
                   "BALANCE_SHEET": (16, 30), "M2": (16, 30)}

# ForexFactory title -> our indicator (USD only). Core PCE m/m removed on purpose:
# its forecast is a monthly %, which would not match our YoY actual.
FF_MAP = {
    "CPI": ["CPI y/y"],
    "CORE_PCE": ["Core PCE Price Index y/y"],
    "NFP": ["Non-Farm Employment Change"],
    "UNRATE": ["Unemployment Rate"],
    "FEDFUNDS": ["Federal Funds Rate"],
}

YF_TICKERS = {
    "US10Y": "^TNX",
    "DXY": "DX-Y.NYB",
    "BTC": "BTC-USD",
    "MSTR": "MSTR",
    "STRC": "STRC",
}


# ---- Card 5 (News Brief / Multi-LLM Fallback) ----

# Google AI Studio
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Groq API
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Ordered provider fallback
NEWS_LLM_PROVIDERS = [
    ("gemini", "gemini-3.8-flash"),
    ("groq", "openai/gpt-oss-120b"),
    ("groq", "qwen/qwen3.8-27b"),
    ("gemini", "gemini-3.5-flash-lite"),
    ("groq", "openai/gpt-oss-20b"),
]

# Retry configuration
LLM_RETRY_DELAYS = (0, 5, 15)
LLM_TIMEOUT = 90

# News slot configuration
SLOT_HOURS = 12
SUMMARY_KEEP_DAYS = 7
NEWS_PER_FEED = 15
NEWS_MAX_PER_CATEGORY = 20
