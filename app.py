"""InsightFlow AI — Streamlit chat UI."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from insightflow.config import settings
from insightflow.execution.executor import reset_engine
from insightflow.knowledge.schema_agent import refresh_schema
from insightflow.llm import LLMClient
from insightflow.memory import Memory
from insightflow.orchestrator import Orchestrator


st.set_page_config(page_title="InsightFlow AI", page_icon="📊", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar
with st.sidebar:
    st.header("InsightFlow AI")
    st.caption("Confidence-aware conversational BI")

    llm = LLMClient()
    st.markdown(f"**LLM provider:** `{llm.provider}` — "
                f"{'✅ available' if llm.available else '⚠️ offline'}")
    st.markdown(f"**Database:** `{settings.database_url}`")

    high = st.slider("Answer threshold",  0.10, 0.95, float(settings.threshold_high), 0.05)
    low  = st.slider("Warn threshold",    0.05, 0.90, float(settings.threshold_low),  0.05)
    settings.threshold_high = high
    settings.threshold_low  = low

    if st.button("Reseed demo data", use_container_width=True):
        import runpy
        runpy.run_path(str(Path(__file__).parent / "data" / "seed.py"),
                       run_name="__main__")
        reset_engine()
        refresh_schema()
        st.success("Demo database reseeded.")

    st.subheader("Try one of these")
    for q in [
        "What is the total revenue?",
        "Show revenue by region",
        "What is the revenue by month?",
        "Why did revenue decrease in July?",
        "What is the gross margin by category?",
        "Top products by revenue",
        "What is the average order value in August?",
        "What is the meaning of life?",
    ]:
        if st.button(q, key=f"eg-{q}", use_container_width=True):
            st.session_state.setdefault("pending", q)
            st.session_state["pending"] = q

# ---------------------------------------------------------------------------
# Session state
if "memory" not in st.session_state:
    st.session_state["memory"] = Memory(maxlen=15)
if "orch" not in st.session_state:
    st.session_state["orch"] = Orchestrator(llm=llm, memory=st.session_state["memory"])
if "history" not in st.session_state:
    st.session_state["history"] = []  # list of InsightResponse

orch: Orchestrator = st.session_state["orch"]

st.title("📊 InsightFlow AI")
st.caption("Ask a business question. I'll answer only when confident.")

# ---------------------------------------------------------------------------
def _decision_style(action: str) -> tuple[str, str]:
    return {
        "ANSWER":  ("🟢", "ANSWER"),
        "WARN":    ("🟡", "WARN"),
        "CLARIFY": ("🔵", "CLARIFY"),
        "ABSTAIN": ("🔴", "ABSTAIN"),
    }.get(action, ("⚪", action))


def _render_response(resp) -> None:
    icon, label = _decision_style(resp.decision.action)
    cols = st.columns([1, 3])
    cols[0].metric(label=f"{icon} Decision", value=label,
                   delta=f"conf {resp.confidence.score:.2f}")
    cols[1].info(resp.decision.reason)

    with st.expander("Confidence signals", expanded=False):
        for name, val in resp.confidence.signals.items():
            st.progress(min(1.0, max(0.0, val)),
                        text=f"{name}: {val:.2f}")

    if resp.decision.action in ("ANSWER", "WARN"):
        st.write(resp.explanation)

        if resp.result.ok and resp.result.rows:
            df = pd.DataFrame(resp.result.rows, columns=resp.result.columns)
            spec = resp.chart
            try:
                if spec["kind"] == "line":
                    fig = px.line(df, x=spec["x"], y=spec["y"], markers=True)
                    st.plotly_chart(fig, use_container_width=True)
                elif spec["kind"] == "bar":
                    fig = px.bar(df, x=spec["x"], y=spec["y"])
                    st.plotly_chart(fig, use_container_width=True)
                elif spec["kind"] == "metric":
                    val = df.iloc[0, -1]
                    st.metric(spec["y"], f"{val:,.2f}" if isinstance(val, (int, float)) else str(val))
            except Exception as e:
                st.warning(f"Could not render chart: {e}")

            with st.expander("Data (first rows)"):
                st.dataframe(df.head(50), use_container_width=True)

        if resp.recommendation:
            st.success(f"💡 Recommendation: {resp.recommendation}")
    else:
        st.warning(resp.explanation)

    with st.expander("Evidence chain"):
        for step in resp.evidence.as_chain():
            st.markdown(f"**{step['step']}**")
            st.write(step["value"])


# ---------------------------------------------------------------------------
# Chat input
prompt = st.chat_input("Ask a question about the sales data")
pending = st.session_state.pop("pending", None)
if pending and not prompt:
    prompt = pending

if prompt:
    try:
        resp = orch.ask(prompt)
        st.session_state["history"].append(resp)
    except Exception as e:
        st.error(f"Something went wrong: {e}")

# ---------------------------------------------------------------------------
# Render history (most recent first)
for resp in reversed(st.session_state["history"]):
    with st.chat_message("user"):
        st.write(resp.question)
    with st.chat_message("assistant"):
        _render_response(resp)

# short conversational memory in footer
with st.expander("Recent turns"):
    for t in st.session_state["memory"].recent():
        st.write(f"- **{t.action}** ({t.confidence:.2f}) — {t.question}")
