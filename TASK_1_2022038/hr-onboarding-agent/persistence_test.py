from __future__ import annotations

import argparse
import json

from langchain_core.messages import HumanMessage

from approval_logic import build_hitl_graph


def _display(values: dict) -> dict:
    out = {}
    for k, v in values.items():
        if k == "messages":
            out[k] = [getattr(m, "content", str(m)) for m in v]
        else:
            out[k] = v
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lab 5 – Persistence test (run twice with the same --thread-id)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--thread-id", required=True, help="Unique session identifier  reuse the same value on the second run")
    args = parser.parse_args()
    config = {"configurable": {"thread_id": args.thread_id}}

    app = build_hitl_graph()
    snapshot = app.get_state(config)

    if snapshot and snapshot.values and snapshot.values.get("pending_action"):
        print(f"\n[thread_id: {args.thread_id}]")
        print("Existing checkpoint found in checkpoint_db.sqlite.")
        print("Restoring previous session WITHOUT re-running the planner...\n")

        print("── Recovered state ──────────────────────────────────────")
        print(json.dumps(_display(snapshot.values), indent=2, default=str))

        action = snapshot.values["pending_action"]
        status = snapshot.values.get("approval_status", "")

        assert action.get("recipient_email"), "recipient_email missing"
        assert action.get("subject"), "subject missing"
        assert action.get("body"), "body missing"
        assert status in {"pending", "approved", "cancelled"}, f"unexpected approval status: '{status}'"

        print("\n✅  Persistence Test : SUCCESS")
        print(f"    Thread '{args.thread_id}' correctly recovered from checkpoint_db.sqlite.")
        print("    The planner did NOT run again  state came purely from the DB.")
        print(f"    Recovered approval status: {status or 'unknown'}\n")
        print("── Continue with approval_logic.py ──────────────────────")
        print(f"  python approval_logic.py --thread-id {args.thread_id} --mode show")
        print(f"  python approval_logic.py --thread-id {args.thread_id} --mode edit --edited-body \"Your revised body.\"")
        print(f"  python approval_logic.py --thread-id {args.thread_id} --mode approve")
        print(f"  python approval_logic.py --thread-id {args.thread_id} --mode cancel")
        return

    print(f"\n[thread_id: {args.thread_id}]")
    print("No existing checkpoint found. Starting a new session.\n")
    print("Enter the details for the high-risk email action:\n")

    recipient = input("  Recipient email  : ").strip()
    subject = input("  Subject          : ").strip()
    body = input("  Body (min 20 ch) : ").strip()

    if not recipient or "@" not in recipient:
        print("Invalid recipient email.")
        return
    if len(subject) < 3:
        print("Subject must be at least 3 characters.")
        return
    if len(body) < 20:
        print(f"Body too short ({len(body)} chars)  minimum 20 required.")
        return

    app.invoke(
        {
            "messages": [HumanMessage(content=f"Initiate onboarding email to {recipient}")],
            "pending_action": {
                "recipient_email": recipient,
                "subject": subject,
                "body": body,
            },
            "approval_status": "pending",
        },
        config=config,
    )

    saved = app.get_state(config)
    print("\n── State saved to checkpoint_db.sqlite ──────────────────")
    print(json.dumps(_display(saved.values), indent=2, default=str))
    print(f"\n✅  Session saved under thread_id '{args.thread_id}'.")
    print("    Stop this script and run it again with the SAME --thread-id")
    print("    to prove the state is recovered from the database:\n")
    print(f"    python persistence_test.py --thread-id {args.thread_id}")


if __name__ == "__main__":
    main()
