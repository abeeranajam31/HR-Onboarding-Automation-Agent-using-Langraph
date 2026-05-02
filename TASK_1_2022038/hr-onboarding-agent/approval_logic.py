from __future__ import annotations

import atexit
import json
import sys
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

try:
    from tools import send_manager_email
    _TOOLS_AVAILABLE = True
except ImportError:
    _TOOLS_AVAILABLE = False

_CHECKPOINTER_CM = None
_CHECKPOINTER: SqliteSaver | None = None


def _close_checkpointer() -> None:
    global _CHECKPOINTER_CM, _CHECKPOINTER
    if _CHECKPOINTER_CM is not None:
        try:
            _CHECKPOINTER_CM.__exit__(None, None, None)
        finally:
            _CHECKPOINTER_CM = None
            _CHECKPOINTER = None

_DEFAULT_EMAIL: dict = {
    "recipient_email": "manager@company.com",
    "subject": "Onboarding Day-1 Execution Confirmation",
    "body": (
        "Hello,\n\nPlease confirm Day-1 execution for the new hire.\n\nRegards,\nHR Operations Agent"
    ),
}


class HITLState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_action: dict
    approval_status: Literal["pending", "approved", "cancelled"]


def planner_node(state: HITLState) -> dict:
    proposed = state.get("pending_action") or {}
    for k, v in _DEFAULT_EMAIL.items():
        proposed.setdefault(k, v)
    return {
        "messages": [AIMessage(content=(
            f"[Planner] HIGH-RISK action proposed: send_manager_email\n"
            f"  To      : {proposed['recipient_email']}\n"
            f"  Subject : {proposed['subject']}\n"
            f"  Body    : {proposed['body']}\n"
            "Status: AWAITING HUMAN APPROVAL"
        ))],
        "pending_action": proposed,
        "approval_status": "pending",
    }


def route_after_planner(state: HITLState) -> Literal["execute_action", "end"]:
    if state.get("approval_status") == "approved":
        return "execute_action"
    return "end"


def execute_action_node(state: HITLState) -> dict:
    action = state["pending_action"]
    if _TOOLS_AVAILABLE:
        result = send_manager_email.invoke({
            "recipient_email": action["recipient_email"],
            "subject": action["subject"],
            "body": action["body"],
        })
    else:
        result = f"[STUB] Email to {action['recipient_email']} | {action['subject']}"
    return {"messages": [AIMessage(content=f"[Executor] {result}")]}


def build_hitl_graph(db_path: str = "checkpoint_db.sqlite"):
    global _CHECKPOINTER_CM, _CHECKPOINTER
    graph = StateGraph(HITLState)
    graph.add_node("planner", planner_node)
    graph.add_node("execute_action", execute_action_node)
    graph.set_entry_point("planner")
    graph.add_conditional_edges(
        "planner", route_after_planner,
        {"execute_action": "execute_action", "end": END},
    )
    graph.add_edge("execute_action", END)
    if _CHECKPOINTER is None:
        _CHECKPOINTER_CM = SqliteSaver.from_conn_string(db_path)
        _CHECKPOINTER = _CHECKPOINTER_CM.__enter__()
        atexit.register(_close_checkpointer)
    return graph.compile(
        checkpointer=_CHECKPOINTER,
        interrupt_before=["execute_action"],
    )


def run_hitl(
    thread_id: str,
    *,
    mode: str = "interactive",
    recipient_email: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    edited_recipient: str | None = None,
    edited_subject: str | None = None,
    edited_body: str | None = None,
) -> None:
    app = build_hitl_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = app.get_state(config)

    print(f"\n[thread_id: {thread_id}]")

    if mode != "interactive":
        if not snapshot or not snapshot.values:
            print("No existing checkpoint found for this thread.")
            return
        print("\n── Saved state ───────────────────────────────────────────")
        print(json.dumps({k: [getattr(m, "content", str(m)) for m in v] if k == "messages" else v for k, v in snapshot.values.items()}, indent=2, default=str))
        print(f"\nApproval status: {snapshot.values.get('approval_status', 'unknown')}")
        if mode == "show":
            return
        if mode == "edit":
            action = dict(snapshot.values.get("pending_action") or {})
            if edited_recipient:
                action["recipient_email"] = edited_recipient
            if edited_subject:
                action["subject"] = edited_subject
            if edited_body:
                action["body"] = edited_body
            app.update_state(config, {"pending_action": action})
            print("Pending action updated.")
            print(json.dumps(action, indent=2))
            return
        if mode in {"approve", "cancel"}:
            if mode == "approve":
                app.update_state(config, {"approval_status": "approved"})
                result = app.invoke(None, config=config)
                print("\n── Result ───────────────────────────────────────────────")
                print(result["messages"][-1].content)
                print("\n✅ HITL flow complete. Email dispatched after human approval.")
            else:
                app.update_state(config, {"approval_status": "cancelled"})
                print("\n🚫 Action CANCELLED. send_manager_email was NOT executed.")
            return
        print(f"Unsupported mode: {mode}")
        return

    print("\n── Step 1: Describe the high-risk email action ──────────")
    print("(The agent will propose this email. You will review it before it sends.)\n")

    recipient = recipient_email or input("  Recipient email  : ").strip()
    subject = subject or input("  Subject          : ").strip()
    body = body or input("  Body (min 20 ch) : ").strip()

    if not recipient or "@" not in recipient:
        print("Invalid email address.")
        return
    if len(subject) < 3:
        print("Subject too short.")
        return
    if len(body) < 20:
        print(f"Body too short ({len(body)} chars, need 20).")
        return

    print("\n── Step 2: Agent planning... ────────────────────────────")
    app.invoke(
        {
            "messages": [HumanMessage(content=f"Send onboarding email to {recipient}")],
            "pending_action": {
                "recipient_email": recipient,
                "subject": subject,
                "body": body,
            },
            "approval_status": "pending",
        },
        config=config,
    )

    snapshot = app.get_state(config)
    action = snapshot.values["pending_action"]

    print("\n── Step 3: SAFETY BREAKPOINT – Review proposed action ───")
    print("  The graph has PAUSED. The email has NOT been sent yet.")
    print(json.dumps(action, indent=2))

    print("\n── Step 4: Edit (optional) ──────────────────────────────")
    new_body = edited_body or input("  New body (press Enter to keep current): ").strip()
    if new_body:
        if len(new_body) < 20:
            print(f"  Body too short ({len(new_body)} chars). Keeping original.")
        else:
            action["body"] = new_body
            app.update_state(config, {"pending_action": action})
            print("  Body updated.")

    print("\n── Step 5: Approve or Cancel ────────────────────────────")
    print("  The email will ONLY be sent if you type 'approve'.")
    decision = "approve" if mode == "interactive" else "cancel"
    if mode == "interactive":
        decision = input("  Decision [approve / cancel]: ").strip().lower()

    if decision == "approve":
        app.update_state(config, {"approval_status": "approved"})
        result = app.invoke(None, config=config)
        print("\n── Result ───────────────────────────────────────────────")
        print(result["messages"][-1].content)
        print("\n✅ HITL flow complete. Email dispatched after human approval.")
    else:
        app.update_state(config, {"approval_status": "cancelled"})
        print("\n🚫 Action CANCELLED. send_manager_email was NOT executed.")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Lab 5 – HITL interactive loop")
    parser.add_argument("--thread-id", required=True, help="Unique session identifier")
    parser.add_argument(
        "--mode",
        choices=["interactive", "show", "edit", "approve", "cancel"],
        default="interactive",
        help="Run the interactive flow or manage an existing checkpoint",
    )
    parser.add_argument("--recipient-email", default=None, help="Initial recipient email for non-interactive runs")
    parser.add_argument("--subject", default=None, help="Initial subject for non-interactive runs")
    parser.add_argument("--body", default=None, help="Initial body for non-interactive runs")
    parser.add_argument("--edited-recipient-email", default=None, help="Updated recipient email for edit mode")
    parser.add_argument("--edited-subject", default=None, help="Updated subject for edit mode")
    parser.add_argument("--edited-body", default=None, help="Updated body for edit mode")
    args = parser.parse_args()
    run_hitl(
        args.thread_id,
        mode=args.mode,
        recipient_email=args.recipient_email,
        subject=args.subject,
        body=args.body,
        edited_recipient=args.edited_recipient_email,
        edited_subject=args.edited_subject,
        edited_body=args.edited_body,
    )


if __name__ == "__main__":
    main()
