BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 77235956591e

CREATE TABLE devices (
    id SERIAL NOT NULL, 
    device_uid VARCHAR(64) NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    location VARCHAR(255), 
    api_key VARCHAR(128) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    last_ping TIMESTAMP WITH TIME ZONE, 
    room_occupied BOOLEAN, 
    last_motion_at TIMESTAMP WITH TIME ZONE, 
    last_distance_cm FLOAT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (api_key), 
    UNIQUE (device_uid)
);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    username VARCHAR(64) NOT NULL, 
    password_hash VARCHAR(255) NOT NULL, 
    full_name VARCHAR(128), 
    is_active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (username)
);

CREATE TABLE alerts (
    id SERIAL NOT NULL, 
    device_id INTEGER NOT NULL, 
    alert_type VARCHAR(20) NOT NULL, 
    message TEXT NOT NULL, 
    is_resolved BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
);

CREATE INDEX ix_alert_device_resolved ON alerts (device_id, is_resolved);

CREATE TABLE control_logs (
    id SERIAL NOT NULL, 
    device_id INTEGER NOT NULL, 
    command VARCHAR(20) NOT NULL, 
    payload JSON, 
    status VARCHAR(20) NOT NULL, 
    triggered_by VARCHAR(64) NOT NULL, 
    detail TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE, 
    acked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
);

CREATE INDEX ix_control_device_time ON control_logs (device_id, created_at);

CREATE TABLE passage_events (
    id SERIAL NOT NULL, 
    device_id INTEGER NOT NULL, 
    event_uid VARCHAR(64) NOT NULL, 
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    min_distance_cm FLOAT, 
    baseline_cm FLOAT, 
    duration_ms INTEGER, 
    received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE, 
    CONSTRAINT uq_passage_device_event UNIQUE (device_id, event_uid)
);

CREATE INDEX ix_passage_device_time ON passage_events (device_id, occurred_at);

CREATE TABLE sensor_data (
    id SERIAL NOT NULL, 
    device_id INTEGER NOT NULL, 
    room_occupied BOOLEAN, 
    motion BOOLEAN, 
    last_motion_at TIMESTAMP WITH TIME ZONE, 
    distance_cm FLOAT, 
    local_count INTEGER, 
    extra JSON, 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE
);

CREATE INDEX ix_sensor_device_time ON sensor_data (device_id, recorded_at);

INSERT INTO alembic_version (version_num) VALUES ('77235956591e') RETURNING alembic_version.version_num;

COMMIT;

