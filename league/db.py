from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    slug TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#b8f34a',
    active INTEGER NOT NULL DEFAULT 1,
    bonus_points INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitions (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    emblem TEXT,
    sort_order INTEGER NOT NULL DEFAULT 100
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    competition_code TEXT NOT NULL,
    season INTEGER,
    matchday INTEGER,
    stage TEXT,
    kickoff_utc TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'SCHEDULED',
    minute INTEGER,
    home_name TEXT NOT NULL,
    home_short TEXT,
    home_tla TEXT,
    home_crest TEXT,
    away_name TEXT NOT NULL,
    away_short TEXT,
    away_tla TEXT,
    away_crest TEXT,
    home_score INTEGER,
    away_score INTEGER,
    last_updated TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, external_id)
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    outcome TEXT NOT NULL CHECK (outcome IN ('H', 'D', 'A')),
    joker INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(player_id, match_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT,
    last_attempt_at TEXT,
    last_success_at TEXT,
    last_error TEXT,
    matches_seen INTEGER NOT NULL DEFAULT 0,
    changed INTEGER NOT NULL DEFAULT 0
);

INSERT OR IGNORE INTO sync_state (id, provider) VALUES (1, NULL);

CREATE INDEX IF NOT EXISTS idx_matches_kickoff ON matches(kickoff_utc);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_competition ON matches(competition_code);
CREATE INDEX IF NOT EXISTS idx_predictions_match ON predictions(match_id);
CREATE INDEX IF NOT EXISTS idx_predictions_player ON predictions(player_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    return conn


@contextmanager
def session(path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: str | Path) -> None:
    with session(path) as conn:
        conn.executescript(SCHEMA)
        # Add manually awarded bonus points to databases created before this column.
        player_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(players)")
        }
        if "bonus_points" not in player_columns:
            conn.execute(
                "ALTER TABLE players ADD COLUMN bonus_points INTEGER NOT NULL DEFAULT 0"
            )
        # Migrate the legacy score-based predictions table to outcome predictions.
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(predictions)")
        }
        if "outcome" not in columns:
            conn.execute("DROP TABLE predictions")
            conn.executescript(SCHEMA)
