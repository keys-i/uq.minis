CREATE TABLE IF NOT EXISTS plans (
  workspace TEXT PRIMARY KEY CHECK (workspace GLOB 'guest:*'),
  revision INTEGER NOT NULL CHECK (revision >= 0),
  data TEXT NOT NULL CHECK (length(data) <= 2097152),
  updated_at INTEGER NOT NULL
) STRICT;

CREATE INDEX IF NOT EXISTS plans_updated ON plans(updated_at);
