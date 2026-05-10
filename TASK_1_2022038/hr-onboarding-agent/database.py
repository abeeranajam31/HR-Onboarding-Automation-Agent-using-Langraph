"""
database.py
===========
SQLite helper module for the HR Onboarding Agent – Final Exam Part A.

Responsibilities
----------------
* Create and migrate the `feedback_logs` table.
* Provide typed helper functions for inserting and querying records.
* Keep all SQL in one place so the rest of the codebase stays clean.

Table: feedback_logs
---------------------
id              INTEGER  PRIMARY KEY AUTOINCREMENT
timestamp       TEXT     ISO-8601 UTC timestamp of the interaction
thread_id       TEXT     Streamlit session thread identifier
message_id      TEXT     Unique message UUID
user_input      TEXT     The raw question asked by the user
agent_response  TEXT     The raw answer returned by the agent
feedback_score  INTEGER  +1 (Good) | -1 (Bad) | NULL (not yet rated)
optional_comment TEXT    Free-text comment for bad responses
error_category  TEXT     Auto-classified failure category
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─── Path resolution ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH: Path = Path(
    os.getenv(
        "FEEDBACK_DB_PATH",
        str(PROJECT_ROOT / "persistence" / "feedback" / "feedback_log.db"),
    )
)

# ─── SQL Statements ────────────────────────────────────────────────────────────
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS feedback_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    thread_id        TEXT    NOT NULL,
    message_id       TEXT    NOT NULL UNIQUE,
    user_input       TEXT    NOT NULL,
    agent_response   TEXT    NOT NULL,
    feedback_score   INTEGER,
    optional_comment TEXT,
    error_category   TEXT
);
"""

_INSERT_INTERACTION_SQL = """
INSERT INTO feedback_logs
    (timestamp, thread_id, message_id, user_input, agent_response,
     feedback_score, optional_comment)
VALUES (?, ?, ?, ?, ?, NULL, NULL);
"""

_UPDATE_FEEDBACK_SQL = """
UPDATE feedback_logs
SET    feedback_score   = ?,
       optional_comment = ?
WHERE  thread_id = ? AND message_id = ?;
"""

_UPDATE_CATEGORY_SQL = """
UPDATE feedback_logs
SET error_category = ?
WHERE id = ?;
"""

_SELECT_ALL_SQL = "SELECT * FROM feedback_logs ORDER BY id ASC;"

_SELECT_NEGATIVE_SQL = """
SELECT id, timestamp, user_input, agent_response, optional_comment, error_category
FROM   feedback_logs
WHERE  feedback_score = -1
ORDER  BY id ASC;
"""

_COUNT_TOTAL_SQL  = "SELECT COUNT(*) FROM feedback_logs;"
_COUNT_NEGATIVE_SQL = "SELECT COUNT(*) FROM feedback_logs WHERE feedback_score = -1;"
_COUNT_POSITIVE_SQL = "SELECT COUNT(*) FROM feedback_logs WHERE feedback_score =  1;"
_COUNT_PENDING_SQL  = "SELECT COUNT(*) FROM feedback_logs WHERE feedback_score IS NULL;"


# ─── Utility ───────────────────────────────────────────────────────────────────

def _utc_now() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # WAL mode for better concurrent read performance
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


# ─── Public API ────────────────────────────────────────────────────────────────

def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """
    Ensure the database file and `feedback_logs` table exist.

    Parameters
    ----------
    db_path : path to the SQLite file (created if missing).

    Returns
    -------
    Resolved Path object to the database file.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as conn:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
    return path


def log_interaction(
    *,
    thread_id: str,
    message_id: str,
    user_input: str,
    agent_response: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """
    Insert a new interaction row (feedback is NULL until the user rates it).

    Returns
    -------
    The rowid (integer primary key) of the inserted row.
    """
    init_db(db_path)
    with closing(_connect(Path(db_path))) as conn:
        cursor = conn.execute(
            _INSERT_INTERACTION_SQL,
            (_utc_now(), thread_id, message_id, user_input, agent_response),
        )
        conn.commit()
        return int(cursor.lastrowid)  # type: ignore[arg-type]


def save_feedback(
    *,
    thread_id: str,
    message_id: str,
    feedback_score: int,
    optional_comment: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> int:
    """
    Update the feedback_score (and optional comment) for an existing row.

    Parameters
    ----------
    feedback_score : +1 for Good, -1 for Bad.

    Returns
    -------
    Number of rows updated (1 on success, 0 if message_id not found).
    """
    init_db(db_path)
    comment = (optional_comment or "").strip() or None
    with closing(_connect(Path(db_path))) as conn:
        cursor = conn.execute(
            _UPDATE_FEEDBACK_SQL,
            (feedback_score, comment, thread_id, message_id),
        )
        conn.commit()
        return cursor.rowcount


def set_error_category(
    row_id: int,
    category: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Set the error_category column for a given row id."""
    with closing(_connect(Path(db_path))) as conn:
        conn.execute(_UPDATE_CATEGORY_SQL, (category, row_id))
        conn.commit()


def fetch_all_interactions(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Return every row in feedback_logs as a list of dicts."""
    init_db(db_path)
    with closing(_connect(Path(db_path))) as conn:
        rows = conn.execute(_SELECT_ALL_SQL).fetchall()
        return [dict(row) for row in rows]


def fetch_negative_interactions(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """Return only rows where feedback_score = -1."""
    init_db(db_path)
    with closing(_connect(Path(db_path))) as conn:
        rows = conn.execute(_SELECT_NEGATIVE_SQL).fetchall()
        return [dict(row) for row in rows]


def get_counts(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, int]:
    """
    Return a summary dict with total, positive, negative, and pending counts.
    """
    init_db(db_path)
    with closing(_connect(Path(db_path))) as conn:
        total    = conn.execute(_COUNT_TOTAL_SQL).fetchone()[0]
        positive = conn.execute(_COUNT_POSITIVE_SQL).fetchone()[0]
        negative = conn.execute(_COUNT_NEGATIVE_SQL).fetchone()[0]
        pending  = conn.execute(_COUNT_PENDING_SQL).fetchone()[0]
    return {
        "total":    total,
        "positive": positive,
        "negative": negative,
        "pending":  pending,
    }


# ─── Schema export (for documentation) ────────────────────────────────────────
SCHEMA_SQL = _CREATE_TABLE_SQL.strip()
