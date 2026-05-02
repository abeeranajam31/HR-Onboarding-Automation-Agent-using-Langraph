from __future__ import annotations

import argparse
import logging
import sys
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from tools import ANALYST_TOOLS, RESEARCHER_TOOLS

researcher_tools = {t.name: t for t in RESEARCHER_TOOLS}
analyst_tools = {t.name: t for t in ANALYST_TOOLS}

logger = logging.getLogger("multi_agent")
logger.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s  %(message)s", datefmt="%H:%M:%S")

_fh = logging.FileHandler("collaboration_trace.log", mode="w", encoding="utf-8")
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
logger.addHandler(_fh)
logger.addHandler(_sh)


class TeamState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    researcher_notes: str
    handoff_done: bool


def _extract_employee_id(text: str) -> str:
    for token in text.replace("?", " ").replace(",", " ").split():
        up = token.upper()
        if up.startswith("EMP") and any(ch.isdigit() for ch in up):
            return up
    return ""


def _pick_researcher_call(user_text: str, employee_id: str) -> dict:
    lower = user_text.lower()
    if "readiness" in lower or "day-1" in lower or "day 1" in lower:
        return {"name": "evaluate_day1_readiness", "args": {"employee_id": employee_id}, "id": "rc1", "type": "tool_call"}
    if "status" in lower or "profile" in lower:
        return {"name": "get_employee_onboarding_status", "args": {"employee_id": employee_id}, "id": "rc2", "type": "tool_call"}
    if "risk" in lower:
        return {"name": "calculate_onboarding_risk", "args": {"employee_id": employee_id}, "id": "rc3", "type": "tool_call"}
    return {"name": "search_onboarding_knowledge", "args": {"query": user_text, "top_k": 3}, "id": "rc4", "type": "tool_call"}


def researcher_node(state: TeamState) -> dict:
    last = state["messages"][-1]
    if isinstance(last, ToolMessage):
        notes = str(last.content)
        logger.info("[Researcher] Tool result received. Packaging notes for Analyst.")
        logger.info("[Researcher] ── HANDOFF TO ANALYST ──────────────────────────")
        return {
            "messages": [AIMessage(content=f"HANDOFF_TO_ANALYST\n{notes}")],
            "researcher_notes": notes,
            "handoff_done": True,
        }

    user_text = next((str(m.content) for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")
    employee_id = _extract_employee_id(user_text)
    call = _pick_researcher_call(user_text, employee_id)

    logger.info(f"[Researcher] Query received: '{user_text}'")
    logger.info(f"[Researcher] Identified employee: {employee_id or '(none)'}")
    logger.info(f"[Researcher] Calling tool: {call['name']}  args={call['args']}")

    return {
        "messages": [AIMessage(content=f"[Researcher] Selecting tool '{call['name']}' to gather evidence.", tool_calls=[call])],
        "handoff_done": False,
    }


def researcher_tool_node(state: TeamState) -> dict:
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": []}

    call = last.tool_calls[0]
    if call["name"] not in researcher_tools:
        result = f"[ACCESS DENIED] '{call['name']}' is not in Researcher's toolset."
        logger.warning(f"[Researcher-Tools] {result}")
    else:
        result = researcher_tools[call["name"]].invoke(call["args"])
        logger.info(f"[Researcher-Tools] '{call['name']}' returned result.")

    return {"messages": [ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"])]}


def analyst_node(state: TeamState) -> dict:
    last = state["messages"][-1]
    if isinstance(last, ToolMessage):
        final = str(last.content)
        logger.info("[Analyst] Draft complete. Producing final response.")
        return {"messages": [AIMessage(content=f"Final collaborative response:\n{final}")]}

    user_text = next((str(m.content) for m in state["messages"] if isinstance(m, HumanMessage)), "")
    employee_id = _extract_employee_id(user_text) or "EMP1001"
    notes = state.get("researcher_notes") or "No researcher notes available."

    logger.info("[Analyst] Received handoff from Researcher.")
    logger.info(f"[Analyst] Notes to synthesize: {notes[:120]}...")
    logger.info(f"[Analyst] Calling tool: draft_manager_email  employee={employee_id}")

    call = {
        "name": "draft_manager_email",
        "args": {"employee_id": employee_id, "context_summary": notes},
        "id": "ac1",
        "type": "tool_call",
    }
    return {"messages": [AIMessage(content="[Analyst] Synthesizing researcher output into manager email.", tool_calls=[call])]}


def analyst_tool_node(state: TeamState) -> dict:
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {"messages": []}

    call = last.tool_calls[0]
    if call["name"] not in analyst_tools:
        result = f"[ACCESS DENIED] '{call['name']}' is not in Analyst's toolset."
        logger.warning(f"[Analyst-Tools] {result}")
    else:
        result = analyst_tools[call["name"]].invoke(call["args"])
        logger.info(f"[Analyst-Tools] '{call['name']}' returned draft.")

    return {"messages": [ToolMessage(content=str(result), tool_call_id=call["id"], name=call["name"])]}


def researcher_router(state: TeamState) -> Literal["researcher_tools", "analyst"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "researcher_tools"
    return "analyst"


def analyst_router(state: TeamState) -> Literal["analyst_tools", "end"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "analyst_tools"
    return "end"


def build_multi_agent_graph():
    g = StateGraph(TeamState)
    g.add_node("researcher", researcher_node)
    g.add_node("researcher_tools", researcher_tool_node)
    g.add_node("analyst", analyst_node)
    g.add_node("analyst_tools", analyst_tool_node)

    g.set_entry_point("researcher")
    g.add_conditional_edges("researcher", researcher_router, {"researcher_tools": "researcher_tools", "analyst": "analyst"})
    g.add_edge("researcher_tools", "researcher")
    g.add_conditional_edges("analyst", analyst_router, {"analyst_tools": "analyst_tools", "end": END})
    g.add_edge("analyst_tools", "analyst")

    return g.compile()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lab 4 – Multi-Agent Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--query", default=None, help="Natural language task (omit to be prompted)")
    args = parser.parse_args()

    query = args.query
    if not query:
        print("\nEnter your task (e.g. 'For EMP1001, assess day-1 readiness and draft manager email')")
        query = input("Query: ").strip()
    if not query:
        print("No query provided.")
        return

    emp_id = _extract_employee_id(query)
    if not emp_id:
        emp_id = input("No employee ID found in query. Enter employee ID (e.g. EMP1001): ").strip().upper()
        if not emp_id:
            print("Employee ID required.")
            return
        query = f"{query} {emp_id}"

    logger.info("=" * 60)
    logger.info(f"Query   : {query}")
    logger.info(f"Employee: {emp_id}")
    logger.info("=" * 60)

    app = build_multi_agent_graph()
    out = app.invoke(
        {"messages": [HumanMessage(content=query)], "researcher_notes": "", "handoff_done": False},
    )

    print("\n" + "=" * 60)
    print("FINAL OUTPUT")
    print("=" * 60)
    print(out["messages"][-1].content)
    print("\n[Trace saved to collaboration_trace.log]")


if __name__ == "__main__":
    main()
