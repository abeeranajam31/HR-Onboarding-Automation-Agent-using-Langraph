"""
analyze_feedback.py
===================
Final Exam Part A — Drift Monitoring & Feedback Loops
------------------------------------------------------
Analysis script that reads the feedback_logs SQLite database and produces
a structured console report covering:

    1. Total interactions
    2. Positive / Negative counts and percentages
    3. Top-3 failed queries (by frequency / severity)
    4. Failure categorization:
         - Hallucination
         - Retrieval Failure
         - Tool Error
         - Wrong Tone
         - Other
    5. Drift signal (rolling negative rate trend)

Usage
-----
    python analyze_feedback.py                  # uses default DB path
    FEEDBACK_DB_PATH=./custom.db python analyze_feedback.py

The script also updates the `error_category` column in the database so
results are persisted for downstream reporting tools and the drift_report.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from textwrap import fill, indent

from database import DEFAULT_DB_PATH, init_db, set_error_category

# ─── Configuration ─────────────────────────────────────────────────────────────
JUDGE_MODEL: str = os.getenv("JUDGE_MODEL", "gpt-4o-mini")
NEGATIVE_RATE_THRESHOLD: float = 0.30   # 30% → flag as drift
TOP_N_FAILED: int = 3

# Allowed category labels (keep consistent across script and Streamlit UI)
ALLOWED_LABELS: set[str] = {
    "Hallucination",
    "Retrieval Failure",
    "Tool Error",
    "Wrong Tone",
    "Other",
}

# ─── Failure categorization ────────────────────────────────────────────────────

def _heuristic_label(user_input: str, agent_response: str, comment: str | None) -> str:
    """
    Rule-based classifier used as a fallback when the LLM judge is unavailable.

    Keyword matching is applied to the combined text of the user query,
    agent response, and optional user comment.
    """
    combined = f"{user_input}\n{agent_response}\n{comment or ''}".lower()

    # Tool Error — explicit runtime failures
    if any(kw in combined for kw in ("error", "failed", "exception", "traceback", "500")):
        return "Tool Error"

    # Wrong Tone — politeness / sentiment issues
    if any(kw in combined for kw in ("tone", "rude", "impolite", "harsh", "aggressive", "stop asking")):
        return "Wrong Tone"

    # Hallucination — the agent invented facts or completed unsupported actions
    if any(kw in combined for kw in (
        "incorrect", "wrong", "halluc", "made up", "invented",
        "didn't happen", "never sent", "fabricated", "fake"
    )):
        return "Hallucination"

    # Retrieval Failure — knowledge base returned nothing useful
    if any(kw in combined for kw in (
        "missing", "incomplete", "not found", "not enough", "no result",
        "couldn't find", "empty", "no data"
    )):
        return "Retrieval Failure"

    return "Other"


def _call_openai_judge(
    user_input: str, agent_response: str, comment: str | None
) -> str | None:
    """
    Call the OpenAI API to classify the failure.

    Returns the label string, or None if the API call fails / key is missing.
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        "You are a strict quality evaluator for an HR AI assistant.\n"
        "Classify the following failed interaction into EXACTLY ONE of these categories:\n"
        "  - Hallucination        (agent invented facts or fake actions)\n"
        "  - Retrieval Failure    (knowledge base returned wrong/no data)\n"
        "  - Tool Error           (a tool raised an exception or returned nothing)\n"
        "  - Wrong Tone           (response was rude, harsh, or inappropriate)\n"
        "  - Other                (does not fit any above category)\n\n"
        f"User Input:\n{user_input}\n\n"
        f"Agent Response:\n{agent_response}\n\n"
        f"User Comment:\n{comment or 'None'}\n\n"
        "Return the label only. No explanation."
    )

    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict evaluator. Return one label only."},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0,
        "max_tokens":  20,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        label = parsed["choices"][0]["message"]["content"].strip().rstrip(".")
        return label if label in ALLOWED_LABELS else None
    except (KeyError, IndexError, json.JSONDecodeError, urllib.error.URLError, TimeoutError):
        return None


def classify_failure(
    row_id: int,
    user_input: str,
    agent_response: str,
    comment: str | None,
    db_path: Path,
) -> str:
    """
    Classify one failed interaction and persist the label to the database.

    Strategy: try LLM judge first, fall back to heuristics.
    """
    label = _call_openai_judge(user_input, agent_response, comment)
    if not label:
        label = _heuristic_label(user_input, agent_response, comment)
    set_error_category(row_id, label, db_path)
    return label


# ─── Report helpers ────────────────────────────────────────────────────────────

def _bar(value: float, width: int = 30, char: str = "█") -> str:
    """Render a simple ASCII bar of proportional width."""
    filled = round(value * width)
    return char * filled + "░" * (width - filled)


def _section(title: str) -> None:
    """Print a styled section header."""
    border = "─" * 60
    print(f"\n{border}")
    print(f"  {title}")
    print(border)


# ─── Main analysis ─────────────────────────────────────────────────────────────

def main(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """
    Full analysis pipeline:

    1. Load all interactions from the database.
    2. Classify every negative interaction.
    3. Print the formatted report.
    """
    path = Path(db_path)
    init_db(path)

    # ── Load data ──────────────────────────────────────────────────────────────
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row

        all_rows = conn.execute(
            "SELECT * FROM feedback_logs ORDER BY id ASC"
        ).fetchall()

        negative_rows = [r for r in all_rows if r["feedback_score"] == -1]
        positive_rows = [r for r in all_rows if r["feedback_score"] ==  1]
        pending_rows  = [r for r in all_rows if r["feedback_score"] is None]

    total    = len(all_rows)
    n_neg    = len(negative_rows)
    n_pos    = len(positive_rows)
    n_pend   = len(pending_rows)
    neg_rate = (n_neg / total) if total > 0 else 0.0
    pos_rate = (n_pos / total) if total > 0 else 0.0

    # ── Print header ───────────────────────────────────────────────────────────
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("\n" + "═" * 62)
    print("  HR ONBOARDING AGENT — FEEDBACK ANALYSIS REPORT")
    print(f"  Generated: {now}")
    print(f"  Database : {path}")
    print("═" * 62)

    # ── Section 1: Overview ────────────────────────────────────────────────────
    _section("1.  INTERACTION SUMMARY")
    print(f"  Total interactions : {total:>5}")
    print(f"  👍 Positive         : {n_pos:>5}  ({pos_rate*100:5.1f}%)  {_bar(pos_rate)}")
    print(f"  👎 Negative         : {n_neg:>5}  ({neg_rate*100:5.1f}%)  {_bar(neg_rate)}")
    print(f"  ⏳ Awaiting feedback : {n_pend:>5}")

    if total == 0:
        print("\n  No interactions found in the database.")
        print("  Run: python generate_sample_feedback.py  to seed example data.")
        return

    # ── Section 2: Classify failures ──────────────────────────────────────────
    _section("2.  FAILURE CLASSIFICATION")

    if n_neg == 0:
        print("  No negative feedback recorded yet — no failures to classify.")
    else:
        print(f"  Classifying {n_neg} negative interaction(s)…\n")
        categories: list[str] = []

        for row in negative_rows:
            label = classify_failure(
                row_id=row["id"],
                user_input=row["user_input"],
                agent_response=row["agent_response"],
                comment=row["optional_comment"],
                db_path=path,
            )
            categories.append(label)
            print(f"  [#{row['id']:>3}] {label:<22} ← {row['user_input'][:55]}")

        category_counts = Counter(categories)
        print()
        print("  ── Distribution ──────────────────────────────────────────")
        for label, count in category_counts.most_common():
            pct   = count / n_neg
            print(f"  {label:<22} {count:>3}  ({pct*100:5.1f}%)  {_bar(pct, width=24)}")

    # ── Section 3: Top-N failed queries ───────────────────────────────────────
    _section(f"3.  TOP {TOP_N_FAILED} FAILED QUERIES")

    if n_neg == 0:
        print("  None recorded.")
    else:
        # Rank by query length (longest = most complex = often hardest for the agent)
        # In production this would use a LLM-scored severity field.
        ranked = sorted(negative_rows, key=lambda r: -len(r["user_input"]))
        for rank, row in enumerate(ranked[:TOP_N_FAILED], start=1):
            wrapped = fill(row["user_input"], width=56)
            indented = indent(wrapped, "     ")
            print(f"\n  #{rank}  Query    : {indented.strip()}")
            print(f"       Response : {row['agent_response'][:80]}…")
            comment = row["optional_comment"] or "—"
            print(f"       Comment  : {comment[:80]}")

    # ── Section 4: Drift signal ────────────────────────────────────────────────
    _section("4.  DRIFT SIGNAL")

    if neg_rate >= NEGATIVE_RATE_THRESHOLD:
        print(f"  ⚠️  DRIFT DETECTED  — Negative rate {neg_rate*100:.1f}% ≥ {NEGATIVE_RATE_THRESHOLD*100:.0f}% threshold")
        print("     Action required: review failure patterns and retrain / re-prompt the agent.")
    else:
        print(f"  ✅  No drift detected — Negative rate {neg_rate*100:.1f}% < {NEGATIVE_RATE_THRESHOLD*100:.0f}% threshold")

    # ── Section 5: Recommendations ────────────────────────────────────────────
    _section("5.  RECOMMENDATIONS")

    if n_neg > 0:
        top_category = category_counts.most_common(1)[0][0]
        recommendations = {
            "Hallucination": (
                "Strengthen the system prompt with an explicit rule:\n"
                "  'Never claim an action has been performed if no tool confirmed it.'\n"
                "  Add a self-check step in the LangGraph agent node."
            ),
            "Retrieval Failure": (
                "Expand the knowledge base with more HR policy documents.\n"
                "  Reduce chunk size to 256 tokens and increase top_k to 5.\n"
                "  Consider adding a hybrid BM25 + dense retrieval pipeline."
            ),
            "Tool Error": (
                "Add try/except wrappers around every tool with graceful fallback messages.\n"
                "  Log tool errors to a separate table for engineering review."
            ),
            "Wrong Tone": (
                "Add a tone-check post-processing step.\n"
                "  Update system prompt to enforce formal, empathetic language.\n"
                "  Test with adversarial frustration-style prompts in the eval pipeline."
            ),
            "Other": (
                "Review the uncategorized failures manually.\n"
                "  Consider adding new heuristic rules or expanding label categories."
            ),
        }
        rec_text = recommendations.get(top_category, "Review logs manually.")
        print(f"  Primary failure type: {top_category}")
        print()
        for line in rec_text.split("\n"):
            print(f"  {line}")
    else:
        print("  Keep monitoring — system is performing within expected thresholds.")

    print("\n" + "═" * 62)
    print("  END OF REPORT")
    print("═" * 62 + "\n")


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
