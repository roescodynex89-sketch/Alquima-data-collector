CREATE TABLE IF NOT EXISTS news_raw (
    id            BIGSERIAL PRIMARY KEY,
    slot_start    TIMESTAMPTZ NOT NULL,
    category      TEXT        NOT NULL,
    source        TEXT        NOT NULL,
    title         TEXT        NOT NULL,
    link          TEXT        NOT NULL,
    published_at  TIMESTAMPTZ,
    summary_raw   TEXT,
    relevant      BOOLEAN,
    sentiment     TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (slot_start, link)
);
CREATE INDEX IF NOT EXISTS idx_news_raw_slot ON news_raw (slot_start);

CREATE TABLE IF NOT EXISTS news_slot_summaries (
    id               BIGSERIAL PRIMARY KEY,
    slot_start       TIMESTAMPTZ NOT NULL UNIQUE,
    slot_end         TIMESTAMPTZ NOT NULL,
    sentiment        TEXT        NOT NULL,
    macro_fed        TEXT        NOT NULL,
    crypto_mstr      TEXT        NOT NULL,
    law_geopolitics  TEXT        NOT NULL,
    btc_impact       TEXT        NOT NULL,
    article_count    INTEGER     NOT NULL DEFAULT 0,
    is_final         BOOLEAN     NOT NULL DEFAULT FALSE,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);