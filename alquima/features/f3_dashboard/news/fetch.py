"""Fetch RSS feeds -> normalized article dicts."""
import html
import logging
import re
from datetime import datetime, timezone

import feedparser

from alquima import config
from alquima.common import http
from . import sources

log = logging.getLogger("alquima.news.fetch")
UA = "Mozilla/5.0 (compatible; AlquimaCollector/1.0)"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_text(s, limit=200):
    s = html.unescape(_TAG.sub(" ", s or ""))
    return _WS.sub(" ", s).strip()[:limit]


def _published(entry):
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        try:
            return datetime(*t[:6], tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def fetch_all(now=None):
    """-> (items, failed_feeds). Items are de-duplicated by link across all feeds."""
    items, seen, failed = [], set(), []
    for category, source, url in sources.FEEDS:
        try:
            r = http.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
            entries = list(feed.entries)[: config.NEWS_PER_FEED]
            n = 0
            for e in entries:
                title = clean_text(e.get("title"), 300)
                link = (e.get("link") or "").strip()
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                items.append({
                    "category": category, "source": source, "title": title, "link": link,
                    "published_at": _published(e) or now,
                    "summary_raw": clean_text(e.get("summary") or e.get("description")),
                })
                n += 1
            log.info("OK   %-28s %2d items", source, n)
            if not entries:
                failed.append(f"{source}: empty feed")
        except Exception as e:
            failed.append(f"{source}: {type(e).__name__}")
            log.warning("FAIL %s: %s", source, type(e).__name__)
    return items, failed