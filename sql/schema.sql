-- Alquima data collector schema (Neon / PostgreSQL). Safe to run more than once.
-- Run:  python -m alquima.db --init

-- Card 1, 2 and M2 (Card 3). One row per indicator per run (history kept; Express reads the latest).
-- `countdown` is NOT stored: it goes stale. Compute it from next_release at read time.
CREATE TABLE IF NOT EXISTS macro_indicators (
    id                   BIGSERIAL PRIMARY KEY,
    indicator            TEXT        NOT NULL,   -- CPI, CORE_PCE, NFP, UNRATE, FEDFUNDS, BALANCE_SHEET, M2
    card                 SMALLINT    NOT NULL,
    series_id            TEXT,
    unit                 TEXT,
    actual               NUMERIC,
    actual_date          DATE,
    previous             NUMERIC,
    forecast             NUMERIC,
    forecast_source      TEXT,                   -- forexfactory | fallback_previous_actual
    forecast_confidence  TEXT,                   -- high | low  (low = fallback, avoid Strong signals)
    forecast_event_date  TIMESTAMPTZ,
    forecast_next        NUMERIC,
    next_release         TIMESTAMPTZ,
    collected_at         TIMESTAMPTZ NOT NULL,
    -- NFP
    avg_last_3m          NUMERIC,
    -- UNRATE / Sahm
    min_prev_12m         NUMERIC,
    sahm_gap             NUMERIC,
    sahm_trigger         BOOLEAN,
    -- FEDFUNDS (proxies, NOT CME FedWatch)
    dgs2                 NUMERIC,
    dff                  NUMERIC,
    dgs2_minus_dff       NUMERIC,
    cut_prob_gt_60       BOOLEAN,
    hike_prob_gt_50      BOOLEAN,
    fed_expectation      TEXT,                   -- CUT | HOLD | HIKE
    -- BALANCE_SHEET
    chg_4w               NUMERIC,
    chg_prev_4w          NUMERIC,
    qe_qt_status         TEXT,                   -- QE_STARTED | QT_SLOWING | QT_ONGOING
    -- M2
    yoy_pct              NUMERIC,
    chg_3m_pct           NUMERIC,
    UNIQUE (indicator, collected_at)
);
CREATE INDEX IF NOT EXISTS idx_macro_ind_latest ON macro_indicators (indicator, collected_at DESC);

-- US10Y, DXY, BTC, MSTR, STRC. Rows older than 90 days are deleted by the sink.
CREATE TABLE IF NOT EXISTS market_prices (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT        NOT NULL,
    ticker        TEXT,
    last          NUMERIC,
    last_date     DATE,
    prev_close    NUMERIC,
    chg_1d        NUMERIC,
    chg_1d_pct    NUMERIC,
    chg_1w        NUMERIC,
    chg_1w_pct    NUMERIC,
    trend_1w      TEXT,                          -- rising | falling
    collected_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (name, collected_at)
);
CREATE INDEX IF NOT EXISTS idx_market_latest ON market_prices (name, collected_at DESC);

-- ForexFactory forecast cache (GitHub Actions has no persistent disk).
CREATE TABLE IF NOT EXISTS ff_events_cache (
    title       TEXT        NOT NULL,
    event_date  TIMESTAMPTZ NOT NULL,
    country     TEXT,
    impact      TEXT,
    forecast    TEXT,
    previous    TEXT,
    actual      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (title, event_date)
);

-- One row per collector run: lets Express/UI show "data stale" warnings.
CREATE TABLE IF NOT EXISTS collector_runs (
    id           BIGSERIAL PRIMARY KEY,
    job          TEXT        NOT NULL,           -- e.g. macro:all, macro:market
    status       TEXT        NOT NULL,           -- ok | partial | error
    rows_written INTEGER     NOT NULL DEFAULT 0,
    error        TEXT,
    finished_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_job ON collector_runs (job, finished_at DESC);

-- Convenience views for Express: newest row per indicator / per market symbol.
CREATE OR REPLACE VIEW macro_latest AS
SELECT DISTINCT ON (indicator) * FROM macro_indicators ORDER BY indicator, collected_at DESC;

CREATE OR REPLACE VIEW market_latest AS
SELECT DISTINCT ON (name) * FROM market_prices ORDER BY name, collected_at DESC;