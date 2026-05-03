-- Extend credit_risk_agent_runs for Tilla Credit Risk Officer v1 (nullable columns — safe on existing rows).
-- Apply manually against your DB after backup. SQLite: run each ALTER separately.

-- SQLite
ALTER TABLE credit_risk_agent_runs ADD COLUMN workflow_status VARCHAR(40) DEFAULT 'Draft';
ALTER TABLE credit_risk_agent_runs ADD COLUMN workflow_note TEXT;
ALTER TABLE credit_risk_agent_runs ADD COLUMN model_score NUMERIC(8,2);
ALTER TABLE credit_risk_agent_runs ADD COLUMN risk_band VARCHAR(8);
ALTER TABLE credit_risk_agent_runs ADD COLUMN rating_gate VARCHAR(16);
ALTER TABLE credit_risk_agent_runs ADD COLUMN recommended_advance_pct NUMERIC(6,2);
ALTER TABLE credit_risk_agent_runs ADD COLUMN recommended_fee_pct NUMERIC(6,3);
ALTER TABLE credit_risk_agent_runs ADD COLUMN policy_status VARCHAR(16);
ALTER TABLE credit_risk_agent_runs ADD COLUMN approval_level_required VARCHAR(64);
ALTER TABLE credit_risk_agent_runs ADD COLUMN can_fund_now BOOLEAN;
ALTER TABLE credit_risk_agent_runs ADD COLUMN model_version VARCHAR(48);
ALTER TABLE credit_risk_agent_runs ADD COLUMN kb_version VARCHAR(48);

-- PostgreSQL (same column set; omit if table created fresh via SQLAlchemy create_all with updated models)
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS workflow_status VARCHAR(40) DEFAULT 'Draft';
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS workflow_note TEXT;
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS model_score NUMERIC(8,2);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS risk_band VARCHAR(8);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS rating_gate VARCHAR(16);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS recommended_advance_pct NUMERIC(6,2);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS recommended_fee_pct NUMERIC(6,3);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS policy_status VARCHAR(16);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS approval_level_required VARCHAR(64);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS can_fund_now BOOLEAN;
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS model_version VARCHAR(48);
-- ALTER TABLE credit_risk_agent_runs ADD COLUMN IF NOT EXISTS kb_version VARCHAR(48);
