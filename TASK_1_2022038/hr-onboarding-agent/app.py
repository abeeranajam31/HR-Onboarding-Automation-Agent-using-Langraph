"""
app.py  –  HR Onboarding Agent  |  Final Exam Part A
=====================================================
Streamlit chat interface with:
  - Real-time chat with the FastAPI / LangGraph backend
  - 👍 / 👎 feedback buttons on every assistant response
  - Optional free-text comment box for negative feedback
  - SQLite persistence (via database.py)
  - Session state to prevent duplicate feedback submissions
  - Analytics sidebar showing live feedback statistics

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import requests
import streamlit as st

# Import our database helpers (database.py in the same directory)
from database import (
    DEFAULT_DB_PATH,
    fetch_all_interactions,
    get_counts,
    init_db,
    log_interaction,
    save_feedback,
)

# ─── Configuration ─────────────────────────────────────────────────────────────
API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000")
PAGE_TITLE = "HR Onboarding Agent"
ACCENT_COLOR = "#4F8EF7"

# ─── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS for a premium look ─────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Import Google Font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Main container */
    .main .block-container {
        padding-top: 1.5rem;
        max-width: 900px;
    }

    /* Header gradient */
    .header-banner {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 12px;
        padding: 1.25rem 1.75rem;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 20px rgba(79,142,247,0.15);
    }
    .header-banner h1 {
        color: #ffffff;
        font-size: 1.65rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.3px;
    }
    .header-banner p {
        color: #94a3b8;
        font-size: 0.85rem;
        margin: 0.3rem 0 0 0;
    }

    /* Chat message bubbles */
    .stChatMessage {
        border-radius: 10px;
        margin-bottom: 0.35rem;
    }

    /* Feedback section */
    .feedback-section {
        background: rgba(79,142,247,0.05);
        border: 1px solid rgba(79,142,247,0.15);
        border-radius: 8px;
        padding: 0.6rem 0.9rem;
        margin-top: 0.5rem;
    }

    /* Metric cards in sidebar */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 0.85rem 1rem;
        margin-bottom: 0.65rem;
        text-align: center;
    }
    .metric-card .value {
        font-size: 2rem;
        font-weight: 700;
        color: #4F8EF7;
    }
    .metric-card .label {
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Success / info banners */
    .stSuccess, .stInfo {
        border-radius: 8px;
    }

    /* Input box */
    .stChatInput textarea {
        border-radius: 8px;
    }

    /* Sidebar header */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    }
    [data-testid="stSidebar"] .css-1d391kg {
        color: #e2e8f0;
    }

    /* Button styles */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(79,142,247,0.3);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── Initialise database ────────────────────────────────────────────────────────
init_db(DEFAULT_DB_PATH)

# ─── Session state bootstrap ───────────────────────────────────────────────────
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())

if "chat_history" not in st.session_state:
    # Each entry: {thread_id, message_id, user_input, agent_response,
    #              feedback_score, optional_comment, timestamp}
    st.session_state.chat_history: list[dict] = []

if "total_sent" not in st.session_state:
    st.session_state.total_sent = 0


# ─── Sidebar: live analytics ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Live Feedback Analytics")
    st.markdown("---")

    counts = get_counts(DEFAULT_DB_PATH)
    total    = counts["total"]
    positive = counts["positive"]
    negative = counts["negative"]
    pending  = counts["pending"]

    neg_pct = round((negative / total * 100), 1) if total > 0 else 0.0
    pos_pct = round((positive / total * 100), 1) if total > 0 else 0.0

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="value">{total}</div>
            <div class="label">Total Interactions</div>
        </div>
        <div class="metric-card" style="border-color:#22c55e44;">
            <div class="value" style="color:#22c55e;">👍 {positive}</div>
            <div class="label">Positive ({pos_pct}%)</div>
        </div>
        <div class="metric-card" style="border-color:#ef444444;">
            <div class="value" style="color:#ef4444;">👎 {negative}</div>
            <div class="label">Negative ({neg_pct}%)</div>
        </div>
        <div class="metric-card" style="border-color:#f59e0b44;">
            <div class="value" style="color:#f59e0b;">{pending}</div>
            <div class="label">Awaiting Feedback</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Drift alert
    if total >= 5 and neg_pct >= 40:
        st.warning(
            f"⚠️ **Drift Alert** — {neg_pct}% negative rate exceeds 40% threshold.\n\n"
            "Run `analyze_feedback.py` for root-cause analysis."
        )
    elif total >= 5 and neg_pct >= 25:
        st.info(f"ℹ️ Negative rate at {neg_pct}%. Monitor closely.")

    st.markdown("---")
    st.markdown("### 🗂️ Session Info")
    st.markdown(f"**Thread:** `{st.session_state.thread_id[:8]}…`")
    st.markdown(
        f"**Started:** {datetime.now().strftime('%H:%M:%S')}"
    )

    if st.button("🔄 New Session", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.chat_history = []
        st.session_state.total_sent = 0
        st.rerun()

    st.markdown("---")
    st.markdown(
        "<small style='color:#64748b;'>Final Exam Part A — Drift Monitoring</small>",
        unsafe_allow_html=True,
    )


# ─── Header banner ─────────────────────────────────────────────────────────────
st.markdown(
    """
    <div class="header-banner">
        <h1>🏢 HR Onboarding Agent</h1>
        <p>Ask onboarding questions and rate each response to help improve the system.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ─── Feedback widget ───────────────────────────────────────────────────────────
def _render_feedback_widget(msg: dict) -> None:
    """
    Render 👍/👎 buttons (or confirmation text) for one message.

    Behaviour
    ---------
    - If feedback already saved → show a read-only label.
    - If not yet rated → show buttons; clicking one saves immediately.
    - If rated -1 (Bad) → show optional comment text area.
    - Duplicate submissions are blocked via msg["feedback_score"].
    """
    thread_id  = msg["thread_id"]
    message_id = msg["message_id"]
    score      = msg.get("feedback_score")

    # Keys for Streamlit widgets (must be stable across reruns)
    btn_good_key   = f"good::{message_id}"
    btn_bad_key    = f"bad::{message_id}"
    comment_key    = f"comment::{message_id}"
    save_cmnt_key  = f"save_comment::{message_id}"

    with st.container():
        st.markdown('<div class="feedback-section">', unsafe_allow_html=True)

        if score == 1:
            st.success("✅ Feedback saved — **Good response**", icon="👍")
        elif score == -1:
            st.error("⚠️ Feedback saved — **Needs improvement**", icon="👎")
            # Show comment box even after feedback is saved so user can add/edit comment
            with st.expander("💬 Add a comment (optional)", expanded=False):
                current_comment = msg.get("optional_comment", "") or ""
                comment_text = st.text_area(
                    "What went wrong?",
                    value=current_comment,
                    key=comment_key,
                    placeholder="e.g. hallucinated action, wrong tone, missing info…",
                    height=80,
                )
                if st.button("💾 Save Comment", key=save_cmnt_key):
                    msg["optional_comment"] = comment_text.strip()
                    save_feedback(
                        thread_id=thread_id,
                        message_id=message_id,
                        feedback_score=-1,
                        optional_comment=comment_text.strip(),
                        db_path=DEFAULT_DB_PATH,
                    )
                    st.success("Comment saved!")
        else:
            # Not yet rated
            st.caption("Was this response helpful?")
            col_good, col_bad, col_spacer = st.columns([1, 1, 4])

            with col_good:
                if st.button("👍 Good", key=btn_good_key, use_container_width=True):
                    msg["feedback_score"] = 1
                    save_feedback(
                        thread_id=thread_id,
                        message_id=message_id,
                        feedback_score=1,
                        db_path=DEFAULT_DB_PATH,
                    )
                    st.rerun()

            with col_bad:
                if st.button("👎 Bad", key=btn_bad_key, use_container_width=True):
                    msg["feedback_score"] = -1
                    save_feedback(
                        thread_id=thread_id,
                        message_id=message_id,
                        feedback_score=-1,
                        db_path=DEFAULT_DB_PATH,
                    )
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)


# ─── Render existing chat history ──────────────────────────────────────────────
for msg in st.session_state.chat_history:
    with st.chat_message("user"):
        st.markdown(msg["user_input"])

    with st.chat_message("assistant"):
        st.markdown(msg["agent_response"])
        _render_feedback_widget(msg)


# ─── Chat input ────────────────────────────────────────────────────────────────
user_prompt = st.chat_input("Ask an onboarding question…  (e.g. 'What is EMP1001 onboarding status?')")

if user_prompt:
    # Show user bubble immediately
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # Call the FastAPI backend
    agent_response = ""
    with st.spinner("🤔 Thinking…"):
        try:
            payload = {
                "message":   user_prompt,
                "thread_id": st.session_state.thread_id,
            }
            resp = requests.post(
                f"{API_BASE_URL}/chat",
                json=payload,
                timeout=90,
            )
            resp.raise_for_status()
            agent_response = resp.json().get("answer", "No answer returned.")
        except requests.exceptions.ConnectionError:
            agent_response = (
                "⚠️ **Backend not reachable.** "
                "Make sure the FastAPI server is running on `http://localhost:8000`.\n\n"
                "Start it with: `python main.py`"
            )
        except requests.exceptions.Timeout:
            agent_response = "⚠️ The request timed out. The agent may be overloaded — please try again."
        except Exception as exc:
            agent_response = f"⚠️ Unexpected error: {exc}"

    # Persist to SQLite
    message_id = str(uuid.uuid4())
    log_interaction(
        thread_id=st.session_state.thread_id,
        message_id=message_id,
        user_input=user_prompt,
        agent_response=agent_response,
        db_path=DEFAULT_DB_PATH,
    )

    # Add to in-memory session history
    new_msg = {
        "thread_id":        st.session_state.thread_id,
        "message_id":       message_id,
        "user_input":       user_prompt,
        "agent_response":   agent_response,
        "feedback_score":   None,
        "optional_comment": "",
        "timestamp":        datetime.utcnow().isoformat(),
    }
    st.session_state.chat_history.append(new_msg)
    st.session_state.total_sent += 1

    # Render assistant bubble
    with st.chat_message("assistant"):
        st.markdown(agent_response)
        _render_feedback_widget(new_msg)
