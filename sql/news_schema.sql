-- Card 5 tables. Run once in the Neon SQL Editor (safe to re-run).
-- All times are UTC. A slot starts at 00:00 or 12:00 UTC = 06:00 / 18:00 Bangladesh time.

-- Raw news of the CURRENT 12h slot only. Rows are deleted when the slot ends.
CREATE TABLE IF NOT EXISTS news_raw (
    id            BIGSERIAL PRIMARY KEY,
    slot_start    TIMESTAMPTZ NOT NULL,
    category      TEXT        NOT NULL,   -- CRYPTO | US_MACRO | CRYPTO_STOCKS | US_LAW_CLARITY | WAR_GEOPOLITICS
    source        TEXT        NOT NULL,
    title         TEXT        NOT NULL,
    link          TEXT        NOT NULL,
    published_at  TIMESTAMPTZ,
    summary_raw   TEXT,
    relevant      BOOLEAN,                -- set by the LLM
    sentiment     TEXT,                   -- BULLISH | BEARISH | NEUTRAL (set by the LLM)
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (slot_start, link)
);
CREATE INDEX IF NOT EXISTS idx_news_raw_slot ON news_raw (slot_start);

-- One summary per 12h slot. Only the last 14 slots (7 days) are kept.
CREATE TABLE IF NOT EXISTS news_slot_summaries (
    id               BIGSERIAL PRIMARY KEY,
    slot_start       TIMESTAMPTZ NOT NULL UNIQUE,
    slot_end         TIMESTAMPTZ NOT NULL,
    sentiment        TEXT        NOT NULL,   -- BULLISH | BEARISH | NEUTRAL
    macro_fed        TEXT        NOT NULL,
    crypto_mstr      TEXT        NOT NULL,
    law_geopolitics  TEXT        NOT NULL,
    btc_impact       TEXT        NOT NULL,
    article_count    INTEGER     NOT NULL DEFAULT 0,
    is_final         BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);