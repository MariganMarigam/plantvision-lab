-- src/plantvision/storage/schema.sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS snapshot (
    image_id       TEXT PRIMARY KEY,                     -- uuid4 hex, server-generated on first receipt
    sha256         TEXT NOT NULL UNIQUE,                 -- content hash == idempotency key
    captured_at    TEXT NOT NULL,                        -- ISO-8601 UTC, device clock
    received_at    TEXT NOT NULL,                        -- ISO-8601 UTC, server clock
    camera_id      TEXT NOT NULL,                        -- e.g. 'phone-01'
    zone_id        TEXT NOT NULL,                        -- e.g. 'shelf-a/tray-1'
    image_path     TEXT NOT NULL,                        -- relative path under data/originals/
    width          INTEGER,
    height         INTEGER,
    byte_size      INTEGER,
    capture_status TEXT NOT NULL DEFAULT 'ok'
                   CHECK (capture_status IN ('ok','corrupt','duplicate')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshot_captured_at ON snapshot(captured_at);
CREATE INDEX IF NOT EXISTS idx_snapshot_zone        ON snapshot(zone_id, captured_at);

CREATE TABLE IF NOT EXISTS processing (
    image_id          TEXT NOT NULL REFERENCES snapshot(image_id) ON DELETE CASCADE,
    pipeline_version  TEXT NOT NULL,
    processing_status TEXT NOT NULL
                      CHECK (processing_status IN ('pending','running','done','failed','skipped')),
    processed_at      TEXT,
    error_message     TEXT,
    PRIMARY KEY (image_id, pipeline_version)
);

CREATE TABLE IF NOT EXISTS measurement (
    measurement_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id         TEXT NOT NULL REFERENCES snapshot(image_id) ON DELETE CASCADE,
    metric_name      TEXT NOT NULL,   -- projected_area_px | roi_fraction_pct | bbox_w | bbox_h | ...
    metric_value     REAL NOT NULL,
    unit             TEXT NOT NULL,   -- px2 | pct | px | ...
    pipeline_version TEXT NOT NULL,
    computed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_measurement_image  ON measurement(image_id);
CREATE INDEX IF NOT EXISTS idx_measurement_metric ON measurement(metric_name, computed_at);

CREATE TABLE IF NOT EXISTS model_version (
    model_version TEXT PRIMARY KEY,
    model_path    TEXT NOT NULL,
    params_json   TEXT,                                   -- JSON: thresholds, ROI, hyperparams
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
