import chromadb
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, date
import pandas as pd
import json

# ── Shared resources ─────────────────────────
chroma_client = chromadb.PersistentClient(path="output/chroma_db")
collection = chroma_client.get_collection("hr_onboarding_kb")
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# =========================================================
# TOOL 1 — Grounding (Vector Search)
# =========================================================
class SearchKBInput(BaseModel):
    query: str = Field(description="Question about HR policies or onboarding")
    doc_type: Optional[str] = Field(default=None)
    top_k: int = Field(default=3, ge=1, le=10)

@tool(args_schema=SearchKBInput)
def search_onboarding_knowledge(query: str, doc_type: Optional[str] = None, top_k: int = 3) -> str:
    """Search HR knowledge base for policies, tasks, or employee info."""
    query_embedding = embeddings.embed_query(query)
    where_filter = {"doc_type": doc_type} if doc_type else None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter
    )

    if not results["documents"][0]:
        return "No results found."

    output = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        output.append(f"[{meta['doc_type']} | {meta['source_file']}]\n{doc}")

    return "\n\n---\n\n".join(output)

# =========================================================
# TOOL 2 — Checklist Generator
# =========================================================
class ChecklistInput(BaseModel):
    role: str
    department: str
    start_date: str

@tool(args_schema=ChecklistInput)
def generate_onboarding_checklist(role: str, department: str, start_date: str) -> str:
    """Generate onboarding checklist with deadlines and urgency."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    today = date.today()
    days_until_start = (start - today).days

    with open("data/checklists/onboarding_master.json") as f:
        data = json.load(f)

    matched_role = next((r for r in data["roles"] if r.lower() in role.lower()), list(data["roles"].keys())[0])
    tasks = data["roles"][matched_role]["tasks"]

    results = []
    for task in tasks:
        due_in = days_until_start - task["due_before_start_days"]
        status = "OVERDUE" if due_in < 0 else "URGENT" if due_in <= 3 else "UPCOMING"
        results.append(f"{status} | {task['task']} (Dept: {task['department']})")

    return "\n".join(results)

# =========================================================
# TOOL 3 — Employee Status Lookup
# =========================================================
class EmployeeStatusInput(BaseModel):
    employee_id: str

@tool(args_schema=EmployeeStatusInput)
def get_employee_onboarding_status(employee_id: str) -> str:
    """Retrieve employee onboarding profile."""
    df = pd.read_csv("data/raw/employees.csv")
    df["employee_id"] = df["employee_id"].astype(str)

    emp = df[df["employee_id"] == employee_id]
    if emp.empty:
        return "Employee not found."

    row = emp.iloc[0]
    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    return (
        f"{row['first_name']} {row['last_name']} — {row['role']} ({row['department']})\n"
        f"Start Date: {row['start_date']} ({days_until_start} days)"
    )

# =========================================================
# TOOL 4 — Day 1 Readiness Evaluator ⭐
# =========================================================
class ReadinessInput(BaseModel):
    employee_id: str

@tool(args_schema=ReadinessInput)
def evaluate_day1_readiness(employee_id: str) -> str:
    """
    Evaluate if employee is ready for Day 1 based on start date proximity
    and checklist urgency.
    """
    df = pd.read_csv("data/raw/employees.csv")
    df["employee_id"] = df["employee_id"].astype(str)
    emp = df[df["employee_id"] == employee_id]

    if emp.empty:
        return "Employee not found."

    row = emp.iloc[0]
    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    score = 100
    blockers = []

    if days_until_start < 3:
        score -= 30
        blockers.append("Very little time before start date")

    if days_until_start < 0:
        score -= 50
        blockers.append("Start date already passed")

    readiness = "READY" if score >= 70 else "AT RISK" if score >= 40 else "NOT READY"

    return (
        f"Day-1 Readiness: {readiness}\n"
        f"Score: {score}/100\n"
        f"Blockers: {', '.join(blockers) if blockers else 'None'}"
    )

# =========================================================
# TOOL 5 — Risk Score Calculator ⭐
# =========================================================
class RiskInput(BaseModel):
    employee_id: str

@tool(args_schema=RiskInput)
def calculate_onboarding_risk(employee_id: str) -> str:
    """
    Calculate onboarding delay risk score (0–100).
    Higher = greater risk.
    """
    df = pd.read_csv("data/raw/employees.csv")
    df["employee_id"] = df["employee_id"].astype(str)
    emp = df[df["employee_id"] == employee_id]

    if emp.empty:
        return "Employee not found."

    row = emp.iloc[0]
    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    risk = 0

    if days_until_start <= 7:
        risk += 40
    elif days_until_start <= 14:
        risk += 20

    if row["employment_type"].lower() == "contract":
        risk += 10

    level = "HIGH" if risk >= 50 else "MEDIUM" if risk >= 25 else "LOW"

    return f"Risk Score: {risk}/100 — {level} risk of onboarding delay"