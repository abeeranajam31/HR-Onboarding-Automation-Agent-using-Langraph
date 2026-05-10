"""
generate_sample_feedback.py
============================
Seeds the feedback_logs database with realistic example interactions.

Run this once before running analyze_feedback.py to populate the database
with a representative set of HR onboarding interactions.

Usage
-----
    python generate_sample_feedback.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from database import DEFAULT_DB_PATH, init_db

# ─── Realistic sample interactions ────────────────────────────────────────────
# Format: (user_input, agent_response, feedback_score, optional_comment)
#   feedback_score: +1 Good | -1 Bad
SAMPLES: list[tuple[str, str, int, str]] = [
    # ── Positive interactions (well-handled) ──────────────────────────────────
    (
        "Show onboarding status for EMP1001",
        "Employee EMP1001 — Priya Sharma — is currently 80% through the onboarding checklist. "
        "Remaining tasks: IT equipment provisioning and Benefits enrollment. "
        "Expected completion: Day 3.",
        1,
        "",
    ),
    (
        "Evaluate Day-1 readiness for EMP1002",
        "Day-1 readiness for EMP1002 — Raj Patel — scores 92/100. "
        "All critical tasks are complete. Minor blocker: email account activation pending IT confirmation.",
        1,
        "",
    ),
    (
        "Who is the manager of EMP1003?",
        "The direct manager of EMP1003 — Alice Johnson — is David Kim (Engineering Lead, eng-lead@company.com).",
        1,
        "",
    ),
    (
        "List all pending IT tasks for EMP1004",
        "Pending IT tasks for EMP1004:\n1. Laptop provisioning\n2. SSO / VPN access setup\n"
        "3. Security badge activation\nEstimated completion: 1–2 business days.",
        1,
        "",
    ),
    (
        "What is the company leave policy?",
        "The company offers 20 days of paid annual leave per calendar year. "
        "Leave accrues monthly at 1.67 days/month. Unused leave may be carried over up to 5 days. "
        "Please refer to the Employee Handbook §4.2 for full details.",
        1,
        "",
    ),
    (
        "Explain the security training deadline for new hires",
        "All new hires must complete the Information Security Awareness training within 48 hours "
        "of their start date. Failure to complete it within 72 hours triggers an automatic "
        "escalation to the new hire's manager.",
        1,
        "",
    ),
    (
        "Summarize onboarding blockers for EMP1005",
        "Current blockers for EMP1005 — Sarah Lee:\n"
        "1. NDA signature pending (DocuSign link sent 2 days ago)\n"
        "2. Background check result awaited (Day 4 expected)\n"
        "Recommend: follow up with Sarah directly via email.",
        1,
        "",
    ),
    # ── Negative interactions (various failure types) ──────────────────────────
    (
        "Calculate the exact tax deduction for EMP1006 this month",
        "I cannot calculate tax deductions in this environment. "
        "Tax calculations require access to the payroll system which is outside my current toolset. "
        "Please contact payroll@company.com or log into the HR payroll portal.",
        -1,
        "Tool should have attempted to calculate but just said it cannot — no alternative was useful.",
    ),
    (
        "Show onboarding status for EMP404",
        "Employee EMP404 has completed all onboarding tasks and is fully active.",
        -1,
        "EMP404 does not exist — the agent fabricated a completion status instead of reporting 'not found'.",
    ),
    (
        "Send a reminder email to the hiring manager for EMP1007",
        "Done. Reminder email sent to the hiring manager.",
        -1,
        "The agent has no email-sending capability — this is a hallucinated action. No email was sent.",
    ),
    (
        "Give me the private salary details for EMP1002",
        "EMP1002 — Raj Patel — salary: $95,000 per annum. Bonus: 10%.",
        -1,
        "Agent disclosed sensitive payroll data without authorization — should have refused the request.",
    ),
    (
        "Can you please speed up the onboarding process? It has been 3 days already!",
        "The process takes as long as it takes. Stop asking.",
        -1,
        "Tone is completely unprofessional and dismissive. Agent should have been empathetic and offered next steps.",
    ),
]


def main() -> None:
    db_path = Path(DEFAULT_DB_PATH)
    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        existing_count = conn.execute("SELECT COUNT(*) FROM feedback_logs").fetchone()[0]
        if existing_count >= 10:
            print(f"Database already contains {existing_count} rows — skipping seed.")
            print(f"Database path: {db_path}")
            return

        import uuid
        inserted = 0
        for idx, (user_input, agent_response, score, comment) in enumerate(SAMPLES, start=1):
            conn.execute(
                """
                INSERT INTO feedback_logs (
                    timestamp, thread_id, message_id,
                    user_input, agent_response, feedback_score, optional_comment
                ) VALUES (
                    datetime('now', ? || ' minutes'),
                    ?,
                    ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    f"-{(len(SAMPLES) - idx) * 15}",      # stagger timestamps backwards in time
                    f"seed-thread-{(idx % 3) + 1}",
                    str(uuid.uuid4()),
                    user_input,
                    agent_response,
                    score,
                    comment.strip() if comment.strip() else None,
                ),
            )
            inserted += 1

        conn.commit()

    print(f"✅  Seeded {inserted} interactions into: {db_path}")
    print(f"    Positive: {sum(1 for _, __, s, ___ in SAMPLES if s == 1)}")
    print(f"    Negative: {sum(1 for _, __, s, ___ in SAMPLES if s == -1)}")
    print("\nRun next: python analyze_feedback.py")


if __name__ == "__main__":
    main()
