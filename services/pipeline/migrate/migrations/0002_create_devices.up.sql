-- Create enum type for device status
DO $$ BEGIN
    CREATE TYPE DEVICE_STATUS AS ENUM ('UNKNOWN', 'ONLINE', 'OFFLINE', 'ERROR');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Create enum type for device type
DO $$ BEGIN
    CREATE TYPE DEVICE_TYPE AS ENUM ('TELEOP_ROBOT', 'REALSENSE_CAMERA', 'ZED_CAMERA', 'ROBOT_OBSERVER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Create devices table
CREATE TABLE devices (
    id VARCHAR(128) PRIMARY KEY NOT NULL,
    type DEVICE_TYPE NOT NULL,
    status DEVICE_STATUS NOT NULL DEFAULT 'UNKNOWN',
    last_heartbeat TIMESTAMPTZ,
    config JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
