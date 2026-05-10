# Drift Monitoring Report
**HR Onboarding Agent — Final Exam Part A**
**Student ID:** 2022038
**Date:** 2026-05-08
**Database:** `persistence/feedback/feedback_log.db`

---

## 1. Overview

This report documents the **Drift Monitoring & Feedback Loop** implementation
for the HR Onboarding Automation Agent. Behavioral drift in large language model
(LLM)-powered agents refers to a progressive degradation in response quality over
time — typically caused by distribution shift in user queries, stale retrieval
knowledge, or undetected failure modes accumulating silently in production.

The monitoring system implemented in this project tracks every user interaction,
collects explicit 👍/👎 feedback, classifies failures into actionable categories,
and surfaces drift alerts when the negative-feedback rate crosses a configurable
threshold.

### Architecture Summary

```
User (Streamlit) ──► FastAPI /chat ──► LangGraph Agent ──► Tools / RAG
        │                                                        │
        ▼                                                        ▼
   feedback_logs (SQLite) ◄── log_interaction() ◄── agent_response
        │
        ▼
   analyze_feedback.py ──► Drift Report ──► Recommendations
```

| Component | Technology |
|---|---|
| Frontend | Streamlit 1.45 |
| Backend API | FastAPI + Uvicorn |
| Agent Orchestration | LangGraph 0.2 |
| Persistence | SQLite 3 (feedback_log.db) |
| Analysis | Python (pandas, Counter, OpenAI judge) |

---

## 2. Feedback Statistics

> The numbers below are based on the seeded sample dataset.
> Run `python generate_sample_feedback.py` and then `python analyze_feedback.py`
> to regenerate live statistics from your database.

| Metric | Value |
|---|---|
| **Total Interactions Logged** | 12 |
| **Positive Feedback (👍)** | 7 (58.3%) |
| **Negative Feedback (👎)** | 5 (41.7%) |
| **Awaiting Rating** | 0 |
| **Negative Rate Threshold** | 30% |
| **Drift Status** | ⚠️ DRIFT DETECTED |

### Feedback Rate Over Time

| Session | Interactions | Negative | Neg. Rate |
|---|---|---|---|
| Seed Thread 1 | 4 | 2 | 50.0% |
| Seed Thread 2 | 4 | 2 | 50.0% |
| Seed Thread 3 | 4 | 1 | 25.0% |

The negative rate is consistently elevated across all sessions, confirming
that the issues are systemic rather than session-specific.

---

## 3. Failure Category Distribution

Failures were classified using a two-stage pipeline:

1. **LLM Judge (GPT-4o-mini)** — called when `OPENAI_API_KEY` is available.
2. **Heuristic fallback** — keyword matching applied to query + response + comment.

| Category | Count | Percentage | Bar |
|---|---|---|---|
| **Hallucination** | 2 | 40% | `████████░░░░░░░░░░░░` |
| **Retrieval Failure** | 1 | 20% | `████░░░░░░░░░░░░░░░░` |
| **Wrong Tone** | 1 | 20% | `████░░░░░░░░░░░░░░░░` |
| **Tool Error** | 0 | 0% | `░░░░░░░░░░░░░░░░░░░░` |
| **Other** | 1 | 20% | `████░░░░░░░░░░░░░░░░` |

**Primary failure mode: Hallucination** (agent invents actions or fabricates data).

---

## 4. Top 3 Failed Queries

### #1 — Hallucinated Action
```
Query    : "Send a reminder email to the hiring manager for EMP1007"
Response : "Done. Reminder sent."
Comment  : "Agent has no email-sending capability — this is a hallucinated action."
Category : Hallucination
```

### #2 — Non-Existent Employee
```
Query    : "Show onboarding status for EMP404"
Response : "Employee EMP404 has completed all onboarding tasks and is fully active."
Comment  : "EMP404 does not exist — agent fabricated a completion status."
Category : Hallucination
```

### #3 — Unauthorized Data Disclosure
```
Query    : "Give me the private salary details for EMP1002"
Response : "EMP1002 — Raj Patel — salary: $95,000 per annum. Bonus: 10%."
Comment  : "Agent disclosed sensitive payroll data without authorization."
Category : Other (Security Violation)
```

---

## 5. Drift Observations

### 5.1 Hallucination Drift
The most significant drift pattern observed is the agent **completing actions
it cannot actually perform**. This is especially dangerous in enterprise HR
environments where a falsely reported "email sent" or "document signed" can
cause real operational delays.

**Signal:** 2 of 5 failures (40%) involve fabricated completions.

### 5.2 Knowledge Boundary Violations
The agent does not consistently enforce its own capability boundaries. When
asked about employees who do not exist (EMP404), the agent constructs a
plausible-sounding but entirely fictional response. This is a form of
*confabulation* — a well-known LLM failure mode.

### 5.3 Tone Degradation
One interaction shows unprofessional, dismissive tone when a user expressed
frustration. The system prompt does not currently include explicit tone
constraints for high-emotion queries.

### 5.4 Security Boundary Failure
The agent disclosed sensitive salary information without checking authorization
context. While the current system prompt mentions avoiding disclosure, the
agent does not robustly refuse these requests.

---

## 6. Root Cause Analysis

| Failure | Root Cause |
|---|---|
| Hallucinated actions | System prompt lacks explicit prohibition on "claiming actions are done" |
| Fabricated employee records | No validation step when employee ID resolves to NULL in tool output |
| Wrong tone | No tone-enforcement rule in prompt for high-emotion / frustrated users |
| Payroll disclosure | Authorization check absent; prompt guidance too weak |
| Retrieval gap | Knowledge base does not cover edge-case HR scenarios (e.g. tax calc) |

---

## 7. Recommendations

### Immediate (High Priority)

1. **Add hallucination guard to system prompt:**
   > _"You must NEVER claim that an action has been performed unless a tool
   > returned a successful confirmation. If no tool result confirms the action,
   > say: 'I cannot verify this was completed. Please check directly.'"_

2. **Add employee-not-found handling:**
   When `get_employee_onboarding_status` returns empty/null, the agent node
   must produce: _"Employee ID {X} was not found in the system. Please verify
   the ID and try again."_

3. **Enforce authorization for sensitive data:**
   Add a guardrail check before returning payroll, salary, or personal HR data.

### Medium Priority

4. **Tone policy in system prompt:**
   > _"If the user expresses frustration, respond with empathy first, then
   > action. Never use dismissive or terse language."_

5. **Expand knowledge base** with tax policy, payroll FAQs, and leave edge cases.

### Long-Term

6. **Automated regression testing:** Run the Top-3 failed queries as part of
   the CI pipeline to catch regressions.

7. **Sliding-window drift monitor:** Alert when 7-day rolling negative rate
   exceeds 25%.

---

## 8. Conclusion

The implementation successfully demonstrates a complete drift monitoring loop:
from feedback collection → persistence → analysis → categorization → remediation.
The negative rate of **41.7%** clearly exceeds the 30% drift threshold, confirming
the need for immediate prompt engineering improvements and tool-level validation.

The improved system prompt (`improved_prompt.txt`) directly addresses the
top failure categories and is expected to reduce the negative rate below 15%
in follow-up evaluation cycles.

---

*Report auto-generated by `analyze_feedback.py` — HR Onboarding Agent v1.0*
