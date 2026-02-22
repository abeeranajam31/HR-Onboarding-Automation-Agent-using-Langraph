# graph.py
from typing import Annotated
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from dotenv import load_dotenv
import os


from tools.tools import (
    search_onboarding_knowledge,
    generate_onboarding_checklist,
    get_employee_onboarding_status,
    evaluate_day1_readiness,
    calculate_onboarding_risk,
    # Add any other project-specific tools here
)
load_dotenv()  # Loads .env file
# ─────────────────────────────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

# ─────────────────────────────────────────────────────────────────
# TOOLS & LLM
# ─────────────────────────────────────────────────────────────────
tools = [
    search_onboarding_knowledge,
    generate_onboarding_checklist,
    get_employee_onboarding_status,
    evaluate_day1_readiness,
    calculate_onboarding_risk,
]

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
llm_with_tools = llm.bind_tools(tools)

SYSTEM_PROMPT = SystemMessage(content="""
You are an intelligent HR Onboarding Automation Agent. Your job is to help HR coordinators 
manage new hire onboarding efficiently.

You have access to these tools:
- search_onboarding_knowledge: Search HR policies, compliance rules, and checklists
- generate_onboarding_checklist: Create a task checklist for a new hire
- get_employee_onboarding_status: Look up an employee's profile and start date
- evaluate_day1_readiness: Assess if an employee is ready for Day 1
- calculate_onboarding_risk: Calculate risk of onboarding delay

Always reason step-by-step. Use tools to ground your answers in real data.
If asked about compliance or policy, always search the knowledge base first.
""")

# ─────────────────────────────────────────────────────────────────
# NODES
# ─────────────────────────────────────────────────────────────────
def agent_node(state: AgentState) -> AgentState:
    """Agent node: sends messages to LLM and gets back a decision."""
    messages = [SYSTEM_PROMPT] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

# ─────────────────────────────────────────────────────────────────
# CONDITIONAL ROUTER
# ─────────────────────────────────────────────────────────────────
def router(state: AgentState) -> str:
    """
    Route to tool execution if the LLM made tool calls,
    otherwise route to END (final answer ready).
    """
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END

# ─────────────────────────────────────────────────────────────────
# BUILD GRAPH
# ─────────────────────────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    # Entry point
    graph.set_entry_point("agent")

    # Conditional routing
    graph.add_conditional_edges(
        "agent",
        router,
        {"tools": "tools", END: END}
    )

    # After tools run → back to agent to reason on results
    graph.add_edge("tools", "agent")

    return graph.compile()

# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from langchain_core.messages import HumanMessage

    agent = build_graph()

    test_queries = [
        "What are the mandatory compliance requirements for new hires?",
        "Generate an onboarding checklist for a Software Engineer in Engineering starting 2025-08-01",
        "Look up the status of employee ID 1001",
        "Evaluate Day-1 readiness for employee ID 1001",
        "Calculate onboarding risk for employee ID 1001"
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"USER: {query}")
        result = agent.invoke({"messages": [HumanMessage(content=query)]})
        print(f"AGENT: {result['messages'][-1].content}")