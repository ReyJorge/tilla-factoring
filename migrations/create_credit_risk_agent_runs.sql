-- TILLA — Credit Risk Agent audit table + login password column (PostgreSQL / Render).
-- Run manually if you do not use Alembic: psql $DATABASE_URL -f migrations/create_credit_risk_agent_runs.sql
-- SQLite dev: prefer letting SQLAlchemy create_all(); adapt JSONB → TEXT if applying raw SQL.

ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

CREATE TABLE IF NOT EXISTS credit_risk_agent_runs (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    user_id INTEGER NOT NULL REFERENCES users(id),
    supplier_name VARCHAR(255) NOT NULL,
    supplier_ico VARCHAR(32) NOT NULL,
    anchor_name VARCHAR(255) NOT NULL,
    anchor_ico VARCHAR(32) NOT NULL,
    invoice_amount NUMERIC(18, 2) NOT NULL,
    scoring_result VARCHAR(8) NOT NULL,
    recommendation VARCHAR(80) NOT NULL,
    confidence_level VARCHAR(40) NOT NULL,
    full_input_json JSONB NOT NULL,
    full_output_json JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_credit_risk_agent_runs_user_created
ON credit_risk_agent_runs (user_id, created_at DESC);
