from __future__ import annotations

from typing import Annotated, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from tools import LAB3_TOOLS

TOOLS = {tool.name: tool for tool in LAB3_TOOLS}


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _latest_user_query(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content)
    return ""


def _extract_employee_id(text: str) -> str:
    for token in text.replace("?", " ").replace(",", " ").split():
        up = token.upper()
        if up.startswith("EMP") and any(ch.isdigit() for ch in up):
            return up
    digits = "".join(ch for ch in text if ch.isdigit())
    return f"EMP{digits}" if digits else "EMP1001"



# ── Keywords that signal actions the agent CANNOT perform ────────────────────
_UNSUPPORTED_ACTIONS = [
    "send email", "send reminder", "send a reminder", "send an email",
    "email manager", "email the manager", "notify manager", "send notification",
    "delete employee", "delete record", "remove employee",
    "fire employee", "terminate employee", "terminate contract",
    "update salary", "change salary", "modify payroll", "edit payroll",
    "give raise", "approve leave", "reject leave",
    "book meeting", "schedule meeting", "create calendar",
]

def _is_unsupported(text: str) -> bool:
    """Return True if the query asks for an action the agent cannot perform."""
    lower = text.lower()
    return any(phrase in lower for phrase in _UNSUPPORTED_ACTIONS)


def _decline_response(user_text: str) -> str:
    """Return a polite refusal message with concrete alternative steps."""
    lower = user_text.lower()

    # Email / reminder
    if any(k in lower for k in ["email", "reminder", "notify", "notification"]):
        return (
            "❌ **I'm not able to send emails or notifications** — "
            "this agent does not have access to a mail or messaging tool.\n\n"
            "✅ **Here's how to do it instead:**\n"
            "1. Log in to the **HR Portal** (hr.company.com)\n"
            "2. Navigate to **Employee → Onboarding → Notifications**\n"
            "3. Click **Send Reminder** next to the employee's name\n"
            "4. The system will email the manager automatically.\n\n"
            "_Tip: You can also ask me to check the employee's onboarding status or day-1 readiness._"
        )

    # Termination / deletion
    if any(k in lower for k in ["fire", "terminate", "delete", "remove"]):
        return (
            "❌ **I'm not able to terminate or delete employee records** — "
            "this is a restricted action requiring HR Director approval.\n\n"
            "✅ **Here's the correct process:**\n"
            "1. Raise a **Separation Request** in the HR system\n"
            "2. Get approval from the **HR Director** and **Legal**\n"
            "3. The Records team will process the deletion after clearance.\n\n"
            "_Contact hr-support@company.com for urgent cases._"
        )

    # Payroll / salary
    if any(k in lower for k in ["salary", "payroll", "raise", "pay"]):
        return (
            "❌ **I'm not able to modify payroll or salary records** — "
            "these changes require Finance team authorization.\n\n"
            "✅ **Here's what to do:**\n"
            "1. Submit a **Compensation Change Request** via the HR Portal\n"
            "2. Your manager and Finance must co-approve\n"
            "3. Changes take effect from the next payroll cycle.\n\n"
            "_Ask me about onboarding status, checklists, or day-1 readiness instead._"
        )

    # Generic fallback for other unsupported actions
    return (
        "❌ **I'm not able to perform that action** — "
        "it falls outside my available tools.\n\n"
        "✅ **What I *can* help you with:**\n"
        "- Check employee onboarding status\n"
        "- Evaluate day-1 readiness\n"
        "- Generate onboarding checklists\n"
        "- Calculate onboarding risk\n"
        "- Search HR knowledge base\n\n"
        "_Please contact HR Support for actions requiring system access._"
    )


def agent_node(state: AgentState) -> AgentState:
    last = state["messages"][-1]

    if isinstance(last, ToolMessage):
        return {"messages": [AIMessage(content=f"Final Answer:\n{last.content}")]}

    user_text = _latest_user_query(state["messages"])
    lower = user_text.lower()
    employee_id = _extract_employee_id(user_text)

    # ── GUARD: decline unsupported actions immediately (no tool call) ─────────
    if _is_unsupported(user_text):
        return {"messages": [AIMessage(content=_decline_response(user_text))]}

    # ── Route to the appropriate tool ─────────────────────────────────────────
    if "risk" in lower:
        call = {"name": "calculate_onboarding_risk", "args": {"employee_id": employee_id}, "id": "r1", "type": "tool_call"}
    elif "day 1" in lower or "day-1" in lower or "readiness" in lower:
        call = {"name": "evaluate_day1_readiness", "args": {"employee_id": employee_id}, "id": "r2", "type": "tool_call"}
    elif "status" in lower or "profile" in lower:
        call = {"name": "get_employee_onboarding_status", "args": {"employee_id": employee_id}, "id": "r3", "type": "tool_call"}
    elif "checklist" in lower or "generate" in lower:
        call = {
            "name": "generate_onboarding_checklist",
            "args": {"role": "Software Engineer", "department": "Engineering", "start_date": "2026-03-10"},
            "id": "r4",
            "type": "tool_call",
        }
    else:
        call = {"name": "search_onboarding_knowledge", "args": {"query": user_text, "top_k": 3}, "id": "r5", "type": "tool_call"}

    return {"messages": [AIMessage(content="Reasoning: selecting best tool for next step.", tool_calls=[call])]}


def tool_node(state: AgentState) -> AgentState:
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": []}

    results: list[ToolMessage] = []
    for call in last.tool_calls:
        tool = TOOLS[call["name"]]
        output = tool.invoke(call.get("args", {}))
        results.append(ToolMessage(content=str(output), tool_call_id=call["id"], name=call["name"]))

    return {"messages": results}


def route_after_agent(state: AgentState) -> Literal["tools", "end"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "end"


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tool_node)
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "end": END})
    g.add_edge("tools", "agent")
    return g.compile()


if __name__ == "__main__":
    app = build_graph()
    result = app.invoke({"messages": [HumanMessage(content="Evaluate Day-1 readiness for EMP1001")]})
    print(result["messages"][-1].content)
