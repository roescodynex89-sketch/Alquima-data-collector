"""12-hour slot logic: assign articles to slots, summarize, finalize + delete old raw, prune old summaries."""
import logging
from datetime import timedelta, timezone

from alquima import config

log = logging.getLogger("alquima.news.slots")
SLOT = timedelta(hours=config.SLOT_HOURS)


def slot_start(dt):
    """Start (UTC) of the 12h slot containing dt: 00:00 or 12:00 UTC (= 06:00 / 18:00 Bangladesh time)."""
    dt = dt.astimezone(timezone.utc)
    return dt.replace(hour=(dt.hour // config.SLOT_HOURS) * config.SLOT_HOURS,
                      minute=0, second=0, microsecond=0)


def process(store, items, now, summarize=None):
    cur = slot_start(now)
    prev = cur - SLOT
    res = {"stored": 0, "summarized": [], "finalized": [], "llm_errors": []}

    # 1) Put articles in their slot by publish time. Late items for the previous slot are still
    #    accepted until that slot is finalized. Everything else is dropped.
    prev_final = store.is_final(prev)
    keep = []
    for it in items:
        s = slot_start(it.get("published_at") or now)
        if s == cur or (s == prev and not prev_final):
            keep.append({**it, "slot_start": s})
    res["stored"] = store.upsert_raw(keep)
    touched = {k["slot_start"] for k in keep}

    # 2) (Re)build the summary of a slot from all its raw articles.
    attempted = set()

    def run_summary(s):
        attempted.add(s)
        raw = store.load_raw(s)
        if not raw:
            return False
        if summarize is None:
            return False
        try:
            out = summarize(raw, s, s + SLOT)
        except Exception as e:
            res["llm_errors"].append(f"{s.isoformat()}: {e}")
            log.error("summary failed for slot %s: %s", s.isoformat(), e)
            return False
        store.set_classification(out["classification"])
        store.upsert_summary(s, s + SLOT, out, is_final=False)
        res["summarized"].append(s)
        return True

    for s in (prev, cur):
        if s == prev and prev_final:
            continue
        if s in touched or (s == prev and store.get_summary(s) is None):
            run_summary(s)

    # 3) Slots that ended: keep only the summary, delete the raw news.
    for s in store.old_raw_slots(cur):
        if store.get_summary(s) is None and s not in attempted and s >= cur - 2 * SLOT:
            run_summary(s)
        if store.get_summary(s) is not None or s < cur - 2 * SLOT:
            store.delete_raw_slot(s)
            res["finalized"].append(s)
        # else: no summary yet (LLM down) -> keep raw, retry next hour
    store.finalize_before(cur)

    # 4) Keep only the last 14 slots (7 days) of summaries.
    store.prune_summaries(cur - timedelta(days=config.SUMMARY_KEEP_DAYS))
    return res