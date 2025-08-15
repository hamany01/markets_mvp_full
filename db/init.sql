-- Timescale initialization + schema
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS prices (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  venue  TEXT,
  tf     TEXT NOT NULL,
  ts     TIMESTAMPTZ NOT NULL,
  open   DOUBLE PRECISION,
  high   DOUBLE PRECISION,
  low    DOUBLE PRECISION,
  close  DOUBLE PRECISION,
  volume DOUBLE PRECISION,
  UNIQUE(symbol, tf, ts)
);
SELECT create_hypertable('prices','ts', if_not_exists=>TRUE);

CREATE TABLE IF NOT EXISTS indicators (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  tf     TEXT NOT NULL,
  ts     TIMESTAMPTZ NOT NULL,
  data   JSONB NOT NULL,
  UNIQUE(symbol, tf, ts)
);

CREATE TABLE IF NOT EXISTS signals (
  id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  tf     TEXT NOT NULL,
  ts     TIMESTAMPTZ NOT NULL,
  rule_id UUID NOT NULL,
  fired  BOOLEAN NOT NULL,
  score  DOUBLE PRECISION,
  detail JSONB
);

CREATE TABLE IF NOT EXISTS alerts (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  symbol TEXT NOT NULL,
  type   TEXT NOT NULL,
  params JSONB NOT NULL,
  channel TEXT NOT NULL,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watchlists (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  name TEXT NOT NULL,
  symbols TEXT[] NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS jobs (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  last_run TIMESTAMPTZ,
  status TEXT,
  meta JSONB
);

CREATE TABLE IF NOT EXISTS providers (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  key_alias TEXT,
  rate_limit JSONB
);
