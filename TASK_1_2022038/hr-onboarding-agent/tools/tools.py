from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from local_store import query_index

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOCAL_INDEX = OUTPUT_DIR / "chroma_db" / "local_index.json"
ACTION_LOG = OUTPUT_DIR / "action_log.jsonl"


def _normalize_employee_id(employee_id: str) -> str:
    value = str(employee_id).strip().upper()
    return value if value.startswith("EMP") else f"EMP{value}"


def _load_employees() -> list[dict]:
    with open(DATA_DIR / "raw" / "employees.csv", "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["employee_id"] = str(row.get("employee_id", "")).upper()
    return rows


def _resolve_employee(rows: list[dict], employee_id: str) -> Optional[dict]:
    normalized = _normalize_employee_id(employee_id)
    raw = str(employee_id).strip().upper()
    for row in rows:
        if row.get("employee_id") in {normalized, raw}:
            return row
    return None


class SearchKBInput(BaseModel):
    query: str = Field(min_length=3, description="Question for grounded retrieval")
    doc_type: Optional[str] = Field(default=None, description="Optional metadata filter by document type")
    department: Optional[str] = Field(default=None, description="Optional metadata filter by department")
    top_k: int = Field(default=3, ge=1, le=10)


@tool(args_schema=SearchKBInput)
def search_onboarding_knowledge(query: str, doc_type: Optional[str] = None, department: Optional[str] = None, top_k: int = 3) -> str:
    """Grounding tool: retrieve relevant onboarding chunks from the local vector index."""
    if not LOCAL_INDEX.exists():
        return "Knowledge index not found. Run ingest_data.py first."

    metadata_filter = None
    if doc_type and department:
        metadata_filter = {"doc_type": doc_type, "department": department}
    elif doc_type:
        metadata_filter = {"doc_type": doc_type}
    elif department:
        metadata_filter = {"department": department}

    rows = query_index(LOCAL_INDEX, query, top_k=top_k, metadata_filter=metadata_filter)
    if not rows:
        return "No matching chunks found."

    lines = []
    for idx, row in enumerate(rows, start=1):
        meta = row["metadata"]
        lines.append(
            f"{idx}. [{meta.get('doc_type', 'unknown')} | {meta.get('source_file', 'unknown')} | {meta.get('department', 'unknown')}]\n{row['content']}"
        )
    return "\n\n---\n\n".join(lines)


class ChecklistInput(BaseModel):
    role: str = Field(min_length=2)
    department: str = Field(min_length=2)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD")


@tool(args_schema=ChecklistInput)
def generate_onboarding_checklist(role: str, department: str, start_date: str) -> str:
    """Action tool: generate a role-specific onboarding checklist with urgency labels."""
    with open(DATA_DIR / "checklists" / "onboarding_master.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    role_keys = list(data["roles"].keys())
    matched_role = next((r for r in role_keys if r.lower() in role.lower()), role_keys[0])

    lines = []
    for task in data["roles"][matched_role]["tasks"]:
        due_in = days_until_start - int(task["due_before_start_days"])
        urgency = "OVERDUE" if due_in < 0 else "URGENT" if due_in <= 3 else "UPCOMING"
        lines.append(f"{urgency} | {task['task']} | Owner: {task['department']} | Request Dept: {department}")
    return "\n".join(lines)


class EmployeeStatusInput(BaseModel):
    employee_id: str = Field(min_length=3, description="Employee ID like EMP1001")


@tool(args_schema=EmployeeStatusInput)
def get_employee_onboarding_status(employee_id: str) -> str:
    """Action tool: fetch employee onboarding profile and timeline."""
    row = _resolve_employee(_load_employees(), employee_id)
    if not row:
        return f"Employee not found: {employee_id}"

    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days
    return (
        f"Employee: {row['first_name']} {row['last_name']} ({row['employee_id']})\n"
        f"Role: {row['role']} | Department: {row['department']}\n"
        f"Start Date: {row['start_date']} ({days_until_start} days from today)\n"
        f"Manager: {row['manager_email']} | Location: {row['location']} | Employment: {row['employment_type']}"
    )


class ReadinessInput(BaseModel):
    employee_id: str = Field(min_length=3)


@tool(args_schema=ReadinessInput)
def evaluate_day1_readiness(employee_id: str) -> str:
    """Action tool: evaluate Day-1 readiness and blockers for a specific employee."""
    row = _resolve_employee(_load_employees(), employee_id)
    if not row:
        return f"Employee not found: {employee_id}"

    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    score = 100
    blockers = []
    if days_until_start < 0:
        score -= 50
        blockers.append("Start date already passed")
    elif days_until_start < 3:
        score -= 30
        blockers.append("Very little time before start date")

    readiness = "READY" if score >= 70 else "AT RISK" if score >= 40 else "NOT READY"
    return f"Day-1 Readiness: {readiness}\nScore: {score}/100\nBlockers: {', '.join(blockers) if blockers else 'None'}"


class RiskInput(BaseModel):
    employee_id: str = Field(min_length=3)


@tool(args_schema=RiskInput)
def calculate_onboarding_risk(employee_id: str) -> str:
    """Action tool: calculate onboarding delay risk score for one employee."""
    row = _resolve_employee(_load_employees(), employee_id)
    if not row:
        return f"Employee not found: {employee_id}"

    start = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
    days_until_start = (start - date.today()).days

    risk = 0
    if days_until_start <= 7:
        risk += 40
    elif days_until_start <= 14:
        risk += 20
    if str(row["employment_type"]).lower() == "contract":
        risk += 10

    level = "HIGH" if risk >= 50 else "MEDIUM" if risk >= 25 else "LOW"
    return f"Risk Score: {risk}/100 | Level: {level}"


class DraftEmailInput(BaseModel):
    employee_id: str = Field(min_length=3)
    context_summary: str = Field(min_length=10)


@tool(args_schema=DraftEmailInput)
def draft_manager_email(employee_id: str, context_summary: str) -> str:
    """Analyst tool: draft manager-facing communication using researcher context."""
    row = _resolve_employee(_load_employees(), employee_id)
    if not row:
        return f"Employee not found: {employee_id}"

    return (
        f"Subject: Onboarding update for {row['first_name']} {row['last_name']}\n\n"
        f"Hello Hiring Manager,\n\n"
        f"Status summary for {row['first_name']} {row['last_name']} ({row['role']}):\n"
        f"{context_summary}\n\n"
        f"Please confirm if we should proceed with final Day-1 execution steps.\n\n"
        f"Regards,\nHR Operations Agent"
    )


class SendEmailInput(BaseModel):
    recipient_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    subject: str = Field(min_length=3)
    body: str = Field(min_length=20)


@tool(args_schema=SendEmailInput)
def send_manager_email(recipient_email: str, subject: str, body: str) -> str:
    """HIGH-RISK ACTION TOOL: simulate sending email and log immutable action record."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "recipient_email": recipient_email,
        "subject": subject,
        "body": body,
        "status": "SENT_SIMULATED",
    }
    with open(ACTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    return f"Email dispatch simulated and logged for {recipient_email}."


LAB3_TOOLS = [
    search_onboarding_knowledge,
    generate_onboarding_checklist,
    get_employee_onboarding_status,
    evaluate_day1_readiness,
    calculate_onboarding_risk,
]

RESEARCHER_TOOLS = [
    search_onboarding_knowledge,
    get_employee_onboarding_status,
    evaluate_day1_readiness,
    calculate_onboarding_risk,
]

ANALYST_TOOLS = [
    draft_manager_email,
]
