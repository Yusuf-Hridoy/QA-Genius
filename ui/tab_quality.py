import json

import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import QualityAnalysis
from prompts import get_qa_prompt
from utils import (
    invoke_with_retry,
    get_score_class,
    get_sprint_score_class,
    get_trend_badge_class,
    build_list_html,
)


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Paste your test execution summary. The AI computes Quality Health '
        "and Sprint Health scores, defect density, MTTR estimates, trend analysis, and assigns "
        "actionable recommendations with owners.</div>",
        unsafe_allow_html=True,
    )

    exec_summary = st.text_area(
        "Test Execution Summary",
        placeholder='e.g. "Sprint 14: 145 passed, 22 failed, 8 blocked. '
                    'Failures in payment module (12), login edge cases (6), mobile responsive (4). '
                    'Blocked tests waiting for sandbox refresh. Same payment failures as Sprint 13."',
        height=120,
        key="qa_input",
    )

    qa_parser = PydanticOutputParser(pydantic_object=QualityAnalysis)

    if st.button("📊 Analyse Quality", key="qa_btn"):
        if not exec_summary.strip():
            st.warning("Please enter your test execution summary.")
        else:
            with st.spinner("Computing quality intelligence..."):
                qa_prompt = get_qa_prompt()
                chain = qa_prompt | model | qa_parser
                try:
                    qa = invoke_with_retry(chain, {
                        "exec_summary": exec_summary,
                        "format_instructions": qa_parser.get_format_instructions(),
                    })
                    st.session_state["qa_result"] = qa
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "qa_result" not in st.session_state:
        return

    qa = st.session_state["qa_result"]

    st.markdown("---")
    st.markdown(
        '<div class="section-title">📊 Quality Intelligence Report</div>',
        unsafe_allow_html=True,
    )

    # ── Executive Scorecards ───────────────────────────────────────────────
    score_class = get_score_class(qa.quality_health_score)
    sprint_class = get_sprint_score_class(qa.sprint_health_score or 0)
    trend_class = get_trend_badge_class(qa.trend_direction or "")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="stat-tile">'
            f'<div class="num {score_class}">{qa.quality_health_score}</div>'
            f'<div class="lbl">Quality Score</div>'
            f'<div style="font-size:0.75rem;color:#64748b;margin-top:0.3rem;">{qa.score_label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="stat-tile">'
            f'<div class="num {sprint_class}">{qa.sprint_health_score or "—"}</div>'
            f'<div class="lbl">Sprint Health</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="stat-tile">'
            f'<div class="num total-color">{qa.pass_rate}</div>'
            f'<div class="lbl">Pass Rate</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c4:
        if qa.trend_direction:
            st.markdown(
                f'<div class="stat-tile">'
                f'<span class="badge {trend_class}" style="font-size:0.85rem;">{qa.trend_direction}</span>'
                f'<div class="lbl" style="margin-top:0.5rem;">Trend</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="stat-tile">'
                f'<div class="num total-color">—</div>'
                f'<div class="lbl">Trend</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Secondary Metrics ──────────────────────────────────────────────────
    sec_cols = st.columns(4)
    metrics = [
        ("Defect Density", qa.defect_density or "—"),
        ("MTTR Estimate", qa.mttr or "—"),
        ("CI/CD Health", qa.ci_cd_health or "—"),
        ("Blocked", f"{qa.blocked} tests"),
    ]
    for col, (label, value) in zip(sec_cols, metrics):
        with col:
            st.markdown(
                f'<div style="text-align:center;padding:0.8rem 0.5rem;'
                f'background:rgba(15,23,42,0.3);border-radius:10px;'
                f'border:1px solid rgba(148,163,184,0.06);">'
                f'<div style="font-family:Space Mono,monospace;font-size:0.9rem;color:#e2e8f0;">{value}</div>'
                f'<div style="font-size:0.65rem;color:#475569;text-transform:uppercase;'
                f'letter-spacing:0.1em;margin-top:0.3rem;">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Stats Grid ─────────────────────────────────────────────────────────
    st.markdown("<div style='margin-top:1rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:0.8rem;">'
        f'<div class="stat-tile"><div class="num pass-color">{qa.passed}</div><div class="lbl">Passed</div></div>'
        f'<div class="stat-tile"><div class="num fail-color">{qa.failed}</div><div class="lbl">Failed</div></div>'
        f'<div class="stat-tile"><div class="num block-color">{qa.blocked}</div><div class="lbl">Blocked</div></div>'
        f'<div class="stat-tile"><div class="num total-color">{qa.total}</div><div class="lbl">Total</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Executive Risk Summary ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div class="glass-card glass-card-accent">'
        f'<div class="label">📋 Executive Risk Summary</div>'
        f'<div class="value">{qa.risk_summary}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Risk Areas & Recommendations ───────────────────────────────────────
    col_r, col_rec = st.columns(2)
    with col_r:
        risk_items = build_list_html(qa.risk_areas, "⚠", "#f87171")
        st.markdown(
            f'<div class="glass-card">'
            f'<div class="label">🔴 High-Risk Areas</div>'
            f'<div class="value" style="margin-top:0.5rem;">{risk_items}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_rec:
        rec_items = build_list_html(qa.recommendations, "→", "#34d399")
        st.markdown(
            f'<div class="glass-card">'
            f'<div class="label">✅ Recommendations</div>'
            f'<div class="value" style="margin-top:0.5rem;">{rec_items}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Action Owners ──────────────────────────────────────────────────────
    if qa.action_owners:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">👤 Action Owners</div>',
            unsafe_allow_html=True,
        )
        owner_colors = {
            "[qa]": "#60a5fa",
            "[dev]": "#34d399",
            "[devops]": "#fbbf24",
            "[product]": "#f472b6",
        }
        for owner_item in qa.action_owners:
            owner_key = owner_item.split("]")[0] + "]" if "]" in owner_item else ""
            owner_lower = owner_key.lower()
            color = owner_colors.get(owner_lower, "#94a3b8")
            st.markdown(
                f'<div style="display:flex;align-items:flex-start;gap:0.6rem;'
                f'padding:0.5rem 0;border-bottom:1px solid #1a2535;">'
                f'<span style="color:{color};font-family:Space Mono,monospace;'
                f'font-size:0.75rem;min-width:5rem;">{owner_key}</span>'
                f'<span style="color:#cbd5e1;font-size:0.9rem;">{owner_item}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Blocker Analysis ───────────────────────────────────────────────────
    if qa.blocker_analysis:
        st.markdown("---")
        st.markdown(
            f'<div class="glass-card glass-card-yellow">'
            f'<div class="label" style="color:#fbbf24;">🚧 Blocker Analysis</div>'
            f'<div class="value">{qa.blocker_analysis}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Flaky Tests ────────────────────────────────────────────────────────
    if qa.flaky_tests:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">🔥 Flaky Test Alerts</div>',
            unsafe_allow_html=True,
        )
        for ft in qa.flaky_tests:
            st.markdown(
                f'<div style="padding:0.5rem 0;padding-left:1rem;">'
                f'<span style="color:#fbbf24;margin-right:0.5rem;">⚡</span>'
                f'<span style="color:#e2e8f0;font-size:0.9rem;">{ft}</span></div>',
                unsafe_allow_html=True,
            )

    # ── Exports ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    d1, d2 = st.columns(2)
    with d1:
        md_content = f"""# Quality Intelligence Report

## Scores
| Metric | Value |
|--------|-------|
| Quality Health Score | {qa.quality_health_score} ({qa.score_label}) |
| Sprint Health Score | {qa.sprint_health_score or 'N/A'} |
| Pass Rate | {qa.pass_rate} |
| Trend Direction | {qa.trend_direction or 'N/A'} |
| Defect Density | {qa.defect_density or 'N/A'} |
| MTTR Estimate | {qa.mttr or 'N/A'} |
| CI/CD Health | {qa.ci_cd_health or 'N/A'} |

## Execution Stats
- **Passed:** {qa.passed}
- **Failed:** {qa.failed}
- **Blocked:** {qa.blocked}
- **Total:** {qa.total}

## Executive Summary
{qa.risk_summary}

## Risk Areas
{chr(10).join([f'- {r}' for r in qa.risk_areas])}

## Recommendations
{chr(10).join([f'- {r}' for r in qa.recommendations])}

## Action Owners
{chr(10).join([f'- {a}' for a in (qa.action_owners or [])]) or 'N/A'}

## Blocker Analysis
{qa.blocker_analysis or 'N/A'}

## Flaky Tests
{chr(10).join([f'- {f}' for f in (qa.flaky_tests or [])]) or 'N/A'}
"""
        st.download_button(
            label="⬇️ Download Markdown Report",
            data=md_content.encode("utf-8"),
            file_name="quality_report.md",
            mime="text/markdown",
            key="qa_md_dl",
        )

    with d2:
        json_content = json.dumps(qa.model_dump(), indent=2)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_content.encode("utf-8"),
            file_name="quality_report.json",
            mime="application/json",
            key="qa_json_dl",
        )
