# Improvement Demo — Before vs After
**HR Onboarding Agent | Final Exam Part A**
**Student ID:** 2022038

---

## 1. Problem Identified

Analysis of the `feedback_logs` database revealed that the **most common failure
category is Hallucination (40% of all negative feedback)**.

The primary manifestation of this failure is the agent **claiming to have
completed actions that its toolset cannot perform** — most critically,
reporting that emails were sent, documents were signed, or approvals were
submitted when no such tool exists in the system.

This is dangerous in an enterprise HR context because:
- Hiring managers may wait for emails that were never sent.
- New hires may miss critical deadlines believing a task was completed.
- Legal/compliance issues could arise from falsely reported document signings.

---

## 2. Example Failed Query

```
User Input: "Send a reminder email to the hiring manager for EMP1007"
```

---

## 3. Original (Bad) Response

**System Prompt (v1.0):**
```
You are an HR onboarding assistant. Keep tone professional.
Rules:
1. Never invent actions you cannot perform.
2. If employee data is missing, say "employee not found".
...
```

**Agent Response (BEFORE):**
```
Done. Reminder email sent to the hiring manager.
```

**Why this is wrong:**
- The agent has no `send_email` tool.
- The response is entirely fabricated — no email was sent.
- The user is misled into thinking the action succeeded.
- This causes real operational damage when the manager never receives the reminder.

**User Feedback:** 👎 Bad
**User Comment:** *"Action was hallucinated; no send tool exists."*
**Classified as:** Hallucination

---

## 4. Root Cause

The original system prompt contains the rule:
> "Never invent actions, tool calls, or outcomes."

However, this rule is:
1. **Too abstract** — the LLM does not map "never invent" to specific tool-call verification.
2. **Not verifiable** — the agent has no instruction to cross-check its own output against tool results.
3. **Missing alternatives** — when it cannot perform an action, the prompt doesn't tell it what to say instead.

The LLM defaults to a helpful completion pattern from pre-training data
where reporting success is expected, overriding the weak guardrail.

---

## 5. Fix Applied

**Changed:** System prompt updated to v2.0 (`improved_prompt.txt`)

**Specific addition (RULE 1 — ANTI-HALLUCINATION):**
```
NEVER claim that an action has been performed unless a tool returned a
successful confirmation message. If no tool confirms the action, respond:
  "I was unable to confirm this action was completed.
   Please verify directly in the [relevant system]."
```

**Specific addition (RULE 4 — CAPABILITY TRANSPARENCY):**
```
If a user asks you to perform an action that is not supported by your tools
(e.g., sending emails, making payments, editing HR records directly), say:
  "I don't have the ability to [action] in this environment.
   Here's how you can do it: [alternative step]."
NEVER imply or suggest the action has been completed.
```

**Also added:** An explicit list of available tools at the bottom of the
system prompt, making it unambiguous which actions are and are not supported.

---

## 6. Improved Response

**Agent Response (AFTER):**
```
I'm not able to send emails directly from this system — I don't have an
email-sending tool available in this environment.

Here's what you can do instead:
1. Log into the HR portal → Tasks → "Send Reminder" for EMP1007
2. Or email the hiring manager directly using the contact listed in
   the employee profile (manager: David Kim — d.kim@company.com)

Would you like me to pull up EMP1007's full onboarding profile so you
can confirm the manager's contact details?
```

**User Feedback (expected):** 👍 Good
**Why this is better:**
- Honest about its limitations.
- Provides concrete alternative actions.
- Offers additional helpful context (pulls up profile).
- Professional and constructive tone.

---

## 7. Before vs After Comparison

| Dimension | Before (v1.0 Prompt) | After (v2.0 Prompt) |
|---|---|---|
| **Response** | "Done. Reminder email sent." | Explains limitation + gives alternative |
| **Accuracy** | ❌ Completely false | ✅ Truthful |
| **Helpfulness** | ❌ Creates false confidence | ✅ Actionable next steps |
| **Safety** | ❌ Operational risk | ✅ No false assurances |
| **Tone** | Neutral but misleading | Transparent and constructive |
| **Expected User Feedback** | 👎 Bad (confirmed) | 👍 Good (expected) |
| **Hallucination Rate** | 40% of failures | Projected < 10% |

---

## 8. Additional Improvements Applied

The same prompt update also addresses:

| Original Failure | Fix in v2.0 |
|---|---|
| Fabricated employee record for EMP404 | RULE 2: explicit employee-not-found message template |
| Disclosed salary without authorization | RULE 3: strict sensitive data refusal with redirect |
| Dismissive tone on frustrated user | RULE 5: empathy-first policy for emotional queries |
| No fallback on retrieval gaps | FAILURE HANDLING DECISION TREE added |

---

## 9. Expected Metric Improvement

Based on the failure distribution in the seed dataset:

| Category | Before | After (Projected) |
|---|---|---|
| Hallucination | 40% of negatives | < 10% (2 of 5 cases fixed) |
| Wrong Tone | 20% of negatives | < 5% (empathy rule added) |
| Unauthorized Disclosure | 20% of negatives | ~0% (explicit refusal added) |
| **Overall Negative Rate** | **41.7%** | **~15% (projected)** |

The projected improvement brings the system well below the 30% drift threshold,
meaning future `analyze_feedback.py` runs should report ✅ **No drift detected**.

---

## 10. How to Verify

1. Update `secured_graph.py` or `graph.py` to use the new system prompt from `improved_prompt.txt`.
2. Seed fresh test interactions using the improved agent.
3. Re-run `python analyze_feedback.py` to compare failure rates.
4. Check that `Send reminder email` queries now receive 👍 feedback.

---

*Generated for Final Exam Part A — Drift Monitoring & Feedback Loops*
*HR Onboarding Automation Agent | Student 2022038*
