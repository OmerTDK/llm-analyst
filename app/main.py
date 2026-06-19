"""Demo UI for llm-analyst: governed natural-language analytics.

Runs against MockLLMClient + SemanticLayerClient so the demo is:
  - Reproducible: same question always produces the same answer.
  - Free: zero LLM API calls.
  - Governed: all answers cite the defining YAML, no raw SQL.

Run with:
    cd /path/to/llm-analyst
    streamlit run app/main.py
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from app.registry import DEMO_PLAN_REGISTRY, EXAMPLE_QUESTIONS, OUT_OF_SCOPE_EXAMPLES
from llm_analyst import GuardedAnalyst, RefusalResponse
from llm_analyst.analyst.models import AnalystAnswer
from llm_analyst.llm.mock import MockLLMClient
from llm_analyst.semantic_client import SemanticLayerClient

# ── Page config ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="llm-analyst demo",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Client initialisation ────────────────────────────────────────────────────────


@st.cache_resource(show_spinner="Initialising semantic layer…")
def _build_analyst() -> GuardedAnalyst:
    """Build GuardedAnalyst once per Streamlit server process.

    SemanticLayerClient runs `mf validate-configs` at construction — this takes
    ~20 s on first run (dbt parse + mf subprocess). st.cache_resource ensures
    it happens once and is shared across all browser sessions.
    """
    platform_root = Path(__file__).resolve().parent.parent / "platform"
    os.chdir(str(platform_root.parent))  # run from repo root for relative paths
    semantic_client = SemanticLayerClient()
    mock_llm = MockLLMClient(DEMO_PLAN_REGISTRY)
    return GuardedAnalyst(llm_client=mock_llm, semantic_client=semantic_client)


def get_analyst() -> GuardedAnalyst:
    """Return the cached GuardedAnalyst (initialised once per server process)."""
    return _build_analyst()


# ── Rendering helpers ────────────────────────────────────────────────────────────


def render_analyst_answer(answer: AnalystAnswer) -> None:
    """Render a governed AnalystAnswer with transparency panel."""
    st.success(answer.prose)
    with st.expander("Governance transparency", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Metric definition**")
            st.markdown(f"- **Name:** `{answer.cited_metric.name}`")
            st.markdown(f"- **Label:** {answer.cited_metric.label}")
            st.markdown(f"- **Type:** `{answer.cited_metric.type}`")
            st.markdown(f"- **Definition:** {answer.cited_metric.description}")
            st.markdown(f"- **Source YAML:** `{Path(answer.cited_metric.source_yaml_path).name}`")
        with col2:
            st.markdown("**Query plan**")
            st.markdown(f"- **Metric:** `{answer.query_plan.metric}`")
            if answer.query_plan.dimensions:
                dims = ", ".join(f"`{d}`" for d in answer.query_plan.dimensions)
                st.markdown(f"- **Dimensions:** {dims}")
            else:
                st.markdown("- **Dimensions:** scalar (no grouping)")
            if answer.query_plan.filters:
                st.markdown(f"- **Filters:** {answer.query_plan.filters}")
            st.markdown(f"- **Rationale:** {answer.query_plan.rationale}")

        st.markdown("**MetricFlow command**")
        st.code(" ".join(answer.query_result.mf_command), language="bash")

        if answer.query_result.rows:
            st.markdown("**Result rows**")
            st.dataframe(answer.query_result.rows, use_container_width=True)


def render_refusal(refusal: RefusalResponse) -> None:
    """Render a RefusalResponse."""
    st.warning(f"Out of scope: {refusal.explanation}")


# ── Sidebar ──────────────────────────────────────────────────────────────────────


def render_sidebar() -> None:
    """Render the sidebar with project info and governed metric list."""
    with st.sidebar:
        st.title("llm-analyst")
        st.caption("Governed natural-language analytics")
        st.divider()
        st.markdown(
            "**How it works**\n\n"
            "Every answer is routed through a governed semantic layer "
            "([MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow)). "
            "The analyst cannot invent metrics or query raw tables. "
            "Out-of-scope questions receive a typed `RefusalResponse`.\n\n"
            "This demo uses `MockLLMClient` — no API key required."
        )
        st.divider()
        st.markdown("**Governed metrics**")
        st.markdown(
            "- `origination_volume`\n"
            "- `default_rate`\n"
            "- `avg_balance`\n"
            "- `portfolio_yield`\n"
            "- `delinquency_rate`\n"
            "- `cpr`\n"
            "- `vintage_loss_curve`"
        )
        st.divider()
        st.markdown("[GitHub](https://github.com/OmerTDK/llm-analyst) · Apache-2.0")


# ── Main ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the Streamlit demo."""
    render_sidebar()

    st.title("Portfolio analytics — governed demo")
    st.caption(
        "Ask a question about the synthetic loan portfolio. "
        "Answers are backed by a MetricFlow semantic layer — no raw SQL, "
        "no hallucinated definitions."
    )

    tab_chat, tab_examples = st.tabs(["Chat", "Example questions"])

    with tab_chat:
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                elif msg.get("type") == "answer":
                    render_analyst_answer(msg["answer"])
                elif msg.get("type") == "refusal":
                    render_refusal(msg["refusal"])
                else:
                    st.markdown(msg.get("content", ""))

        if prompt := st.chat_input("Ask a portfolio analytics question…"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Querying semantic layer…"):
                    analyst = get_analyst()
                    result = analyst.ask(prompt)

                if isinstance(result, RefusalResponse):
                    render_refusal(result)
                    st.session_state.messages.append(
                        {"role": "assistant", "type": "refusal", "refusal": result}
                    )
                else:
                    render_analyst_answer(result)
                    st.session_state.messages.append(
                        {"role": "assistant", "type": "answer", "answer": result}
                    )

    with tab_examples:
        st.subheader("In-scope questions (will be answered)")
        for q in EXAMPLE_QUESTIONS:
            if st.button(q, key=f"ex_{hash(q)}"):
                st.session_state.messages = []
                st.session_state.messages.append({"role": "user", "content": q})
                analyst = get_analyst()
                result = analyst.ask(q)
                if isinstance(result, RefusalResponse):
                    st.session_state.messages.append(
                        {"role": "assistant", "type": "refusal", "refusal": result}
                    )
                else:
                    st.session_state.messages.append(
                        {"role": "assistant", "type": "answer", "answer": result}
                    )
                st.rerun()

        st.divider()
        st.subheader("Out-of-scope questions (will be refused)")
        for q in OUT_OF_SCOPE_EXAMPLES:
            st.markdown(f"- `{q}`")


if __name__ == "__main__":
    main()
