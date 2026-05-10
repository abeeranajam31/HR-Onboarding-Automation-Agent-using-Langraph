# Part A Analysis Report

## Feedback Logging
- Logging backend: SQLite (`feedback_log.db`)
- Required fields captured:
  - `user_input`
  - `agent_response`
  - `feedback` (stored as `feedback_score`, where +1=Good, -1=Bad)

## Analysis Output (`python analyze.py`)
- Total responses: 12
- Negative feedback: 5
- Top 3 failed queries:
  1. `Calculate tax deduction for EMP003`
  2. `Show onboarding status for EMP404`
  3. `Send reminder email to manager`

## Interpretation
- The failure pattern indicates weak handling of unsupported actions and edge-case entity resolution.
- A smaller but meaningful portion of failure is tone-related.
