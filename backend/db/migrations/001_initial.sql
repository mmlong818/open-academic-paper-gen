CREATE TABLE IF NOT EXISTS paper_tasks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic         VARCHAR(500) NOT NULL,
    language      VARCHAR(10)  NOT NULL DEFAULT 'zh',
    collab_mode   VARCHAR(20)  NOT NULL DEFAULT 'key_gates',
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending',
    current_phase INT          NOT NULL DEFAULT 0,
    state_snapshot JSONB       NOT NULL DEFAULT '{}',
    error_message TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_paper_tasks_status ON paper_tasks(status);
