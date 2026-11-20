"""Storage for Card 5. MemoryStore = dry run (--sink csv). DbStore = Neon (--sink db)."""
import logging

log = logging.getLogger("alquima.news.store")


class MemoryStore:
    def __init__(self):
        self.raw, self.summaries, self._id = [], {}, 0

    def is_final(self, s):
        x = self.summaries.get(s)
        return bool(x and x["is_final"])

    def get_summary(self, s):
        return self.summaries.get(s)

    def upsert_raw(self, items):
        have = {(r["slot_start"], r["link"]) for r in self.raw}
        n = 0
        for it in items:
            k = (it["slot_start"], it["link"])
            if k in have:
                continue
            self._id += 1
            self.raw.append({**it, "id": self._id, "relevant": None, "sentiment": None})
            have.add(k)
            n += 1
        return n

    def load_raw(self, s):
        return [r for r in self.raw if r["slot_start"] == s]

    def set_classification(self, cls):
        by_id = {r["id"]: r for r in self.raw}
        for i, rel, senti in cls:
            if i in by_id:
                by_id[i]["relevant"], by_id[i]["sentiment"] = rel, senti

    def upsert_summary(self, s, e, out, is_final=False):
        old = self.summaries.get(s, {})
        self.summaries[s] = {
            "slot_start": s, "slot_end": e, "sentiment": out["sentiment"],
            "macro_fed": out["macro_fed"], "crypto_mstr": out["crypto_mstr"],
            "law_geopolitics": out["law_geopolitics"], "btc_impact": out["btc_impact"],
            "article_count": out["article_count"], "is_final": is_final or old.get("is_final", False),
        }

    def old_raw_slots(self, before):
        return sorted({r["slot_start"] for r in self.raw if r["slot_start"] < before})

    def delete_raw_slot(self, s):
        self.raw = [r for r in self.raw if r["slot_start"] != s]

    def finalize_before(self, before):
        for s, x in self.summaries.items():
            if s < before:
                x["is_final"] = True

    def prune_summaries(self, upto):
        """Delete summaries with slot_start <= upto."""
        for s in [s for s in self.summaries if s <= upto]:
            del self.summaries[s]


class DbStore:
    """Tables news_raw / news_slot_summaries (see sql/news_schema.sql)."""

    def __init__(self):
        from alquima import db
        self.conn = db.connect()
        self.conn.autocommit = True

    def close(self):
        self.conn.close()

    def _one(self, sql, params):
        return self.conn.execute(sql, params).fetchone()

    def is_final(self, s):
        row = self._one("SELECT is_final FROM news_slot_summaries WHERE slot_start = %s", (s,))
        return bool(row and row[0])

    def get_summary(self, s):
        row = self._one("SELECT sentiment, is_final FROM news_slot_summaries WHERE slot_start = %s", (s,))
        return {"sentiment": row[0], "is_final": row[1]} if row else None

    def upsert_raw(self, items):
        if not items:
            return 0
        sql = ("INSERT INTO news_raw (slot_start, category, source, title, link, published_at, summary_raw) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (slot_start, link) DO NOTHING")
        rows = [(i["slot_start"], i["category"], i["source"], i["title"], i["link"],
                 i["published_at"], i["summary_raw"]) for i in items]
        with self.conn.cursor() as cur:
            cur.executemany(sql, rows)
        return len(rows)

    def load_raw(self, s):
        cur = self.conn.execute(
            "SELECT id, category, source, title, link, published_at, summary_raw "
            "FROM news_raw WHERE slot_start = %s ORDER BY published_at DESC", (s,))
        keys = ("id", "category", "source", "title", "link", "published_at", "summary_raw")
        return [dict(zip(keys, r)) for r in cur.fetchall()]

    def set_classification(self, cls):
        if not cls:
            return
        with self.conn.cursor() as cur:
            cur.executemany("UPDATE news_raw SET relevant = %s, sentiment = %s WHERE id = %s",
                            [(rel, senti, i) for i, rel, senti in cls])

    def upsert_summary(self, s, e, out, is_final=False):
        self.conn.execute(
            "INSERT INTO news_slot_summaries (slot_start, slot_end, sentiment, macro_fed, crypto_mstr, "
            "law_geopolitics, btc_impact, article_count, is_final, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now()) "
            "ON CONFLICT (slot_start) DO UPDATE SET slot_end = EXCLUDED.slot_end, "
            "sentiment = EXCLUDED.sentiment, macro_fed = EXCLUDED.macro_fed, "
            "crypto_mstr = EXCLUDED.crypto_mstr, law_geopolitics = EXCLUDED.law_geopolitics, "
            "btc_impact = EXCLUDED.btc_impact, article_count = EXCLUDED.article_count, "
            "is_final = news_slot_summaries.is_final OR EXCLUDED.is_final, updated_at = now()",
            (s, e, out["sentiment"], out["macro_fed"], out["crypto_mstr"], out["law_geopolitics"],
             out["btc_impact"], out["article_count"], is_final))

    def old_raw_slots(self, before):
        cur = self.conn.execute("SELECT DISTINCT slot_start FROM news_raw WHERE slot_start < %s "
                                "ORDER BY slot_start", (before,))
        return [r[0] for r in cur.fetchall()]

    def delete_raw_slot(self, s):
        self.conn.execute("DELETE FROM news_raw WHERE slot_start = %s", (s,))

    def finalize_before(self, before):
        self.conn.execute("UPDATE news_slot_summaries SET is_final = TRUE "
                          "WHERE slot_start < %s AND is_final = FALSE", (before,))

    def prune_summaries(self, upto):
        self.conn.execute("DELETE FROM news_slot_summaries WHERE slot_start <= %s", (upto,))