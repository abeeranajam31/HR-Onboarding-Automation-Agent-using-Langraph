from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from feedback_store import DEFAULT_FEEDBACK_DB, init_feedback_db


def main() -> None:
    db_path = Path(DEFAULT_FEEDBACK_DB)
    init_feedback_db(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT user_input, feedback_score FROM feedback_logs ORDER BY id ASC"
        ).fetchall()

    total_responses = len(rows)
    negatives = [row["user_input"] for row in rows if row["feedback_score"] == -1]
    failed_counts = Counter(negatives)
    top_three = failed_counts.most_common(3)

    print(f"Database: {db_path}")
    print(f"Total responses: {total_responses}")
    print(f"Negative feedback: {len(negatives)}")
    print("Top 3 failed queries:")
    if not top_three:
        print("- None")
    for query, count in top_three:
        print(f"- {query} ({count})")


if __name__ == "__main__":
    main()
