from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_FEEDBACK_DB = Path(
    os.getenv("FEEDBACK_DB_PATH", PROJECT_ROOT / "persistence/feedback/feedback_log.db")
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_feedback_db(db_path: str | Path = DEFAULT_FEEDBACK_DB) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                user_input TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                feedback_score INTEGER,
                optional_comment TEXT,
                error_category TEXT
            )
            """
        )
        conn.commit()
    return path


def log_interaction(
    *,
    thread_id: str,
    message_id: str,
    user_input: str,
    agent_response: str,
    db_path: str | Path = DEFAULT_FEEDBACK_DB,
) -> int:
    init_feedback_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO feedback_logs (
                timestamp, thread_id, message_id, user_input, agent_response, feedback_score, optional_comment
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
            """,
            (utc_timestamp(), thread_id, message_id, user_input, agent_response),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_feedback(
    *,
    thread_id: str,
    message_id: str,
    feedback_score: int,
    optional_comment: str | None = None,
    db_path: str | Path = DEFAULT_FEEDBACK_DB,
) -> int:
    init_feedback_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE feedback_logs
            SET feedback_score = ?, optional_comment = ?
            WHERE thread_id = ? AND message_id = ?
            """,
            (
                feedback_score,
                (optional_comment or "").strip() or None,
                thread_id,
                message_id,
            ),
        )
        conn.commit()
        return cursor.rowcount


def fetch_feedback_rows(db_path: str | Path = DEFAULT_FEEDBACK_DB) -> list[dict[str, Any]]:
    init_feedback_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM feedback_logs ORDER BY id ASC").fetchall()
        return [dict(row) for row in rows]
