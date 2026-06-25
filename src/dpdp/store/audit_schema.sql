CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    logged_at TIMESTAMPTZ NOT NULL,
    subject_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    request_basis TEXT NOT NULL,
    outcome_variant TEXT NOT NULL,
    escalate_reason TEXT,
    refuse_reason TEXT,
    refuse_detail TEXT,
    certificate JSONB,
    actions JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS processor_actions (
    id BIGSERIAL PRIMARY KEY,
    audit_log_id BIGINT NOT NULL REFERENCES audit_log (id),
    location_id TEXT NOT NULL,
    state TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
