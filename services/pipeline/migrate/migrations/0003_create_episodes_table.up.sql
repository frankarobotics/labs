-- Create custom enum types for episodes
-- Episodes represent recorded data collection sessions where operators perform tasks

-- Episode lifecycle: INIT -> RECORDING -> RECORDED -> SAVED (or DISCARDED/ERROR)
DO $$ BEGIN
    CREATE TYPE EPISODE_STATUS AS ENUM ('INIT', 'RECORDING', 'RECORDED', 'SAVED', 'DISCARDED', 'ERROR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Manual review outcome after data collection
DO $$ BEGIN
    CREATE TYPE EPISODE_LABEL AS ENUM ('REVIEW_SUCCESS', 'REVIEW_FAILED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Processing pipeline status
DO $$ BEGIN
    CREATE TYPE EPISODE_PROCESSED AS ENUM ('DEFAULT', 'SUCCESS', 'ERROR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Shipping status
DO $$ BEGIN
    CREATE TYPE EPISODE_SHIPPED AS ENUM ('DEFAULT', 'SUCCESS', 'ERROR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Create episodes table
-- Episodes are data collection sessions where an operator performs a task
-- task_id references tasks from YAML configuration (config_tasks.yml), not a database table
CREATE TABLE episodes (
    -- Note: Consider upgrading to PostgreSQL 18+ to use built-in uuidv7() for better performance
    -- and time-ordered UUIDs. See: https://www.postgresql.org/docs/18/datatype-uuid.html
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL,  -- References task from YAML config, no FK constraint
    station_id VARCHAR(128) DEFAULT '',
    status EPISODE_STATUS NOT NULL,
    label EPISODE_LABEL,  -- Optional manual review label
    processed EPISODE_PROCESSED NOT NULL DEFAULT 'DEFAULT',
    shipped EPISODE_SHIPPED NOT NULL DEFAULT 'DEFAULT',
    object_url TEXT,  -- URL to stored episode data (e.g., MCAP files)
    message TEXT DEFAULT '',  -- Human-readable status/error message
    tags JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_episodes_task_id ON episodes (task_id);


CREATE INDEX idx_episodes_station_id ON episodes (station_id);

CREATE INDEX idx_episodes_status ON episodes (status);

CREATE INDEX idx_episodes_label ON episodes (label);

CREATE INDEX idx_episodes_processed ON episodes (processed);

CREATE INDEX idx_episodes_shipped ON episodes (shipped);

-- No foreign key constraint - task_id references YAML config, not database table
