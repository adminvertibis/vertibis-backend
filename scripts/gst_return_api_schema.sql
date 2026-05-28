-- Additive PostgreSQL schema for Vertibis GST Return API ingestion.
-- Safe to run after the existing Vertibis schema is present.

ALTER TABLE clients
  ADD COLUMN IF NOT EXISTS gst_username VARCHAR(100);

CREATE TABLE IF NOT EXISTS gst_auth_sessions (
  id UUID PRIMARY KEY,
  client_id UUID NOT NULL REFERENCES clients(id),
  partner_id UUID NOT NULL REFERENCES partners(id),
  gstin VARCHAR(15) NOT NULL,
  gst_username VARCHAR(100) NOT NULL,
  auth_token_encrypted TEXT,
  status VARCHAR(30) DEFAULT 'otp_requested',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  expires_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_gst_auth_sessions_client_id
  ON gst_auth_sessions(client_id);

CREATE INDEX IF NOT EXISTS ix_gst_auth_sessions_gstin
  ON gst_auth_sessions(gstin);

CREATE TABLE IF NOT EXISTS gst_fetch_batches (
  id UUID PRIMARY KEY,
  client_id UUID NOT NULL REFERENCES clients(id),
  partner_id UUID NOT NULL REFERENCES partners(id),
  financial_year VARCHAR(20),
  period_from VARCHAR(6),
  period_to VARCHAR(6),
  fetch_mode VARCHAR(30) DEFAULT 'single',
  total_periods INTEGER DEFAULT 0,
  total_api_calls INTEGER DEFAULT 0,
  successful_calls INTEGER DEFAULT 0,
  failed_calls INTEGER DEFAULT 0,
  estimated_cost DOUBLE PRECISION DEFAULT 0,
  status VARCHAR(30) DEFAULT 'processing',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_gst_fetch_batches_client_id
  ON gst_fetch_batches(client_id);

CREATE INDEX IF NOT EXISTS ix_gst_fetch_batches_partner_id
  ON gst_fetch_batches(partner_id);

CREATE TABLE IF NOT EXISTS gst_api_fetch_logs (
  id UUID PRIMARY KEY,
  batch_id UUID REFERENCES gst_fetch_batches(id),
  client_id UUID NOT NULL REFERENCES clients(id),
  gstin VARCHAR(15) NOT NULL,
  gst_username VARCHAR(100) NOT NULL,
  return_type VARCHAR(30) NOT NULL,
  action VARCHAR(30) NOT NULL,
  period VARCHAR(6),
  endpoint VARCHAR(600),
  success BOOLEAN DEFAULT FALSE,
  status_code INTEGER,
  error_message VARCHAR(500),
  estimated_cost DOUBLE PRECISION DEFAULT 0,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_gst_api_fetch_logs_batch_id
  ON gst_api_fetch_logs(batch_id);

CREATE INDEX IF NOT EXISTS ix_gst_api_fetch_logs_client_id
  ON gst_api_fetch_logs(client_id);

CREATE INDEX IF NOT EXISTS ix_gst_api_fetch_logs_period
  ON gst_api_fetch_logs(period);

CREATE TABLE IF NOT EXISTS gst_return_raw_data (
  id UUID PRIMARY KEY,
  batch_id UUID REFERENCES gst_fetch_batches(id),
  client_id UUID NOT NULL REFERENCES clients(id),
  gstin VARCHAR(15) NOT NULL,
  period VARCHAR(6) NOT NULL,
  return_type VARCHAR(30) NOT NULL,
  action VARCHAR(30) NOT NULL,
  raw_json JSONB NOT NULL,
  provider VARCHAR(80) DEFAULT 'charteredinfo_gst_return',
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_gst_return_raw_data_client_period
  ON gst_return_raw_data(client_id, period);

CREATE INDEX IF NOT EXISTS ix_gst_return_raw_data_batch_id
  ON gst_return_raw_data(batch_id);

CREATE TABLE IF NOT EXISTS gst_return_normalized_data (
  id UUID PRIMARY KEY,
  batch_id UUID REFERENCES gst_fetch_batches(id),
  client_id UUID NOT NULL REFERENCES clients(id),
  gstin VARCHAR(15) NOT NULL,
  period VARCHAR(6) NOT NULL,
  return_type VARCHAR(30) NOT NULL,
  normalized_json JSONB NOT NULL,
  fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_gst_return_normalized_client_period
  ON gst_return_normalized_data(client_id, period);

CREATE INDEX IF NOT EXISTS ix_gst_return_normalized_batch_id
  ON gst_return_normalized_data(batch_id);

