import pandas as pd

from tools.tools import (
    search_onboarding_knowledge,
    generate_onboarding_checklist,
    get_employee_onboarding_status,
    evaluate_day1_readiness,
    calculate_onboarding_risk,
)

df = pd.read_csv("data/raw/employees.csv")
print("\nAvailable Employee IDs:", df["employee_id"].tolist())

print("\n🔎 TEST 1 — KB Search")
print(search_onboarding_knowledge.invoke({"query": "mandatory compliance"}))

print("\n📋 TEST 2 — Checklist")
print(generate_onboarding_checklist.invoke({
    "role": "Software Engineer",
    "department": "Engineering",
    "start_date": "2026-03-10"
}))

print("\n👤 TEST 3 — Employee Status")
print(get_employee_onboarding_status.invoke({"employee_id": "EMP1001"}))

print("\n✅ TEST 4 — Readiness")
print(evaluate_day1_readiness.invoke({"employee_id": "EMP1001"}))

print("\n📊 TEST 5 — Risk Score")
print(calculate_onboarding_risk.invoke({"employee_id": "EMP1001"}))