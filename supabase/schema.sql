-- ═══════════════════════════════════════════════════════════════
-- SOVEREIGN AGENTS — SUPABASE SCHEMA
-- Run this in: Supabase Dashboard > SQL Editor > New Query
-- ═══════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for text search

-- ─── MAIN SESSIONS TABLE ─────────────────────────────────────────
CREATE TABLE agent_sessions (
    id                   UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    config_name          TEXT        NOT NULL,
    input_text           TEXT,
    agent_turns          JSONB,
    final_output         TEXT,
    verification_status  TEXT        DEFAULT 'IN_PROGRESS',
    tags                 TEXT[]      DEFAULT '{}',
    total_turns          INTEGER     DEFAULT 0,
    summary              TEXT        -- auto-generated summary (optional, for future use)
);

-- ─── INDEXES ────────────────────────────────────────────────────
CREATE INDEX idx_sessions_config      ON agent_sessions(config_name);
CREATE INDEX idx_sessions_created     ON agent_sessions(created_at DESC);
CREATE INDEX idx_sessions_tags        ON agent_sessions USING GIN(tags);
CREATE INDEX idx_sessions_status      ON agent_sessions(verification_status);
CREATE INDEX idx_sessions_input_trgm  ON agent_sessions USING GIN(input_text gin_trgm_ops);
CREATE INDEX idx_sessions_output_trgm ON agent_sessions USING GIN(final_output gin_trgm_ops);

-- ─── ROW LEVEL SECURITY ─────────────────────────────────────────
ALTER TABLE agent_sessions ENABLE ROW LEVEL SECURITY;

-- Service role (your Modal backend) has full access
CREATE POLICY "service_role_full_access" ON agent_sessions
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- ─── USEFUL VIEWS ────────────────────────────────────────────────

-- Recent sessions summary (used by the UI history tab)
CREATE VIEW sessions_summary AS
SELECT
    id,
    created_at,
    config_name,
    LEFT(input_text, 200)   AS input_preview,
    LEFT(final_output, 400) AS output_preview,
    verification_status,
    tags,
    total_turns
FROM agent_sessions
ORDER BY created_at DESC;

-- Sessions per config (usage stats)
CREATE VIEW config_usage_stats AS
SELECT
    config_name,
    COUNT(*)                                          AS total_sessions,
    COUNT(*) FILTER (WHERE verification_status = 'VERIFIED') AS verified_count,
    MAX(created_at)                                   AS last_used,
    ROUND(AVG(total_turns), 1)                        AS avg_turns
FROM agent_sessions
GROUP BY config_name
ORDER BY total_sessions DESC;

-- ─── VERIFY SETUP ────────────────────────────────────────────────
-- Run after creating: should return 0 rows (empty table, no errors)
SELECT * FROM agent_sessions LIMIT 1;
SELECT * FROM config_usage_stats;
