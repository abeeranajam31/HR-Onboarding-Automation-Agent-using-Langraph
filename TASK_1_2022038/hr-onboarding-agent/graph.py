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


def agent_node(state: AgentState) -> AgentState:
    last = state["messages"][-1]

    if isinstance(last, ToolMessage):
        return {"messages": [AIMessage(content=f"Final Answer:\n{last.content}")]}

    user_text = _latest_user_query(state["messages"])
    lower = user_text.lower()
    employee_id = _extract_employee_id(user_text)

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
