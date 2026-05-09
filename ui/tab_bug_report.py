import json

import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import BugReport
from prompts import get_bug_prompt
from utils import (
    invoke_with_retry,
    get_severity_badge_class,
    get_root_cause_badge_class,
    get_regression_risk_class,
    build_steps_html,
)


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Paste raw, messy bug notes. The AI transforms them into a '
        "production-grade bug report with root cause analysis, business impact assessment, "
        "and JIRA-ready exports.</div>",
        unsafe_allow_html=True,
    )

    raw_bug = st.text_area(
        "Raw Bug Notes",
        placeholder='e.g. "login fails on chrome when clicking the button fast, happens 3/5 times, '
                    'user stuck on blank screen, should go to dashboard"',
        height=120,
        key="bug_input",
    )

    bug_parser = PydanticOutputParser(pydantic_object=BugReport)

    if st.button("🐛 Format Bug Report", key="bug_btn"):
        if not raw_bug.strip():
            st.warning("Please enter some bug notes.")
        else:
            with st.spinner("Analyzing and formatting bug report..."):
                bug_prompt = get_bug_prompt()
                chain = bug_prompt | model | bug_parser
                try:
                    bug = invoke_with_retry(chain, {
                        "raw_bug": raw_bug,
                        "format_instructions": bug_parser.get_format_instructions(),
                    })
                    st.session_state["bug_result"] = bug
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "bug_result" not in st.session_state:
        return

    bug = st.session_state["bug_result"]

    st.markdown("---")
    st.markdown(
        '<div class="section-title">🐛 Bug Report</div>',
        unsafe_allow_html=True,
    )

    # ── Executive Summary ──────────────────────────────────────────────────
    badge_class = get_severity_badge_class(bug.severity)
    rc_class = get_root_cause_badge_class(bug.root_cause_category or "")
    rr_class = get_regression_risk_class(bug.regression_risk or "")

    badges_html = f'<span class="badge {badge_class}">{bug.severity}</span>'
    if bug.root_cause_category:
        badges_html += f' <span class="badge {rc_class}">{bug.root_cause_category}</span>'
    if bug.regression_risk:
        badges_html += f' <span class="badge {rr_class}">Regression: {bug.regression_risk}</span>'

    st.markdown(
        f'<div class="glass-card glass-card-accent">'
        f'<div class="label">Bug Title</div>'
        f'<div class="value" style="font-size:1.15rem;font-weight:700;color:#e2e8f0;">{bug.title}</div>'
        f'<div style="margin-top:0.7rem;display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap;">'
        f'{badges_html}'
        f'<span style="font-family:Space Mono,monospace;font-size:0.75rem;color:#475569;">'
        f'Reproducibility: {bug.reproducibility_rate}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Impact Analysis ────────────────────────────────────────────────────
    if bug.business_impact or bug.affected_users or bug.related_areas:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">💼 Impact Analysis</div>',
            unsafe_allow_html=True,
        )

        imp_col1, imp_col2 = st.columns(2)
        with imp_col1:
            if bug.business_impact:
                st.markdown(
                    f'<div class="glass-card glass-card-red">'
                    f'<div class="label" style="color:#f87171;">Business Impact</div>'
                    f'<div class="value">{bug.business_impact}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if bug.affected_users:
                st.markdown(
                    f'<div class="glass-card">'
                    f'<div class="label">Affected Users</div>'
                    f'<div class="value">{bug.affected_users}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        with imp_col2:
            if bug.related_areas:
                st.markdown(
                    f'<div class="glass-card">'
                    f'<div class="label">Related Areas</div>'
                    f'<div class="value">{"<br>• ".join([""] + bug.related_areas)[5:]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if bug.workaround:
                st.markdown(
                    f'<div class="glass-card glass-card-yellow">'
                    f'<div class="label" style="color:#fbbf24;">Workaround</div>'
                    f'<div class="value">{bug.workaround}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Environment & Evidence ─────────────────────────────────────────────
    st.markdown("---")
    env_col1, env_col2 = st.columns(2)
    with env_col1:
        st.markdown(
            f'<div class="glass-card">'
            f'<div class="label">🖥️ Environment Details</div>'
            f'<div class="value">{bug.environment_details}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with env_col2:
        if bug.screenshot_annotations:
            annotations_html = "".join([
                f'<div style="padding:0.35rem 0;font-size:0.85rem;color:#cbd5e1;">'
                f'<span style="color:#fbbf24;margin-right:0.4rem;">📸</span>{ann}</div>'
                for ann in bug.screenshot_annotations
            ])
            st.markdown(
                f'<div class="glass-card">'
                f'<div class="label">Screenshot Annotations</div>'
                f'<div class="value">{annotations_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Steps to Reproduce ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">🔁 Steps to Reproduce</div>',
        unsafe_allow_html=True,
    )

    for i, step in enumerate(bug.steps_to_reproduce, 1):
        st.markdown(
            f'<div style="padding:0.4rem 0;padding-left:0.5rem;">'
            f'<span style="display:inline-block;width:1.8rem;height:1.8rem;line-height:1.8rem;'
            f'text-align:center;border-radius:50%;background:rgba(59,130,246,0.15);'
            f'color:#60a5fa;font-family:Space Mono,monospace;font-size:0.75rem;'
            f'margin-right:0.6rem;">{i}</span>'
            f'<span style="color:#e2e8f0;font-size:0.92rem;">{step}</span></div>',
            unsafe_allow_html=True,
        )

    # ── Actual vs Expected ─────────────────────────────────────────────────
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<div class="glass-card glass-card-red">'
            f'<div class="label" style="color:#f87171;">❌ Actual Result</div>'
            f'<div class="value">{bug.actual_result}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="glass-card glass-card-green">'
            f'<div class="label" style="color:#34d399;">✅ Expected Result</div>'
            f'<div class="value">{bug.expected_result}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Suggested Fix ──────────────────────────────────────────────────────
    if bug.suggested_fix:
        st.markdown("---")
        st.markdown(
            f'<div class="glass-card glass-card-green">'
            f'<div class="label" style="color:#34d399;">💡 Suggested Fix</div>'
            f'<div class="value">{bug.suggested_fix}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── JIRA Labels ────────────────────────────────────────────────────────
    if bug.jira_labels:
        st.markdown("---")
        labels_html = " ".join([
            f'<span style="display:inline-block;padding:0.25rem 0.7rem;border-radius:4px;'
            f'background:rgba(139,92,246,0.1);color:#a78bfa;font-size:0.78rem;'
            f'font-family:Space Mono,monospace;margin-right:0.35rem;margin-bottom:0.35rem;">'
            f'{label}</span>'
            for label in bug.jira_labels
        ])
        st.markdown(
            f'<div style="margin-top:0.5rem;">'
            f'<span style="font-family:Space Mono,monospace;font-size:0.7rem;color:#475569;'
            f'text-transform:uppercase;letter-spacing:0.1em;margin-right:0.5rem;">JIRA Labels:</span>'
            f'{labels_html}</div>',
            unsafe_allow_html=True,
        )

    # ── Downloads ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    d1, d2 = st.columns(2)
    with d1:
        md_content = f"""# {bug.title}

| Field | Value |
|-------|-------|
| **Severity** | {bug.severity} |
| **Reproducibility** | {bug.reproducibility_rate} |
| **Root Cause** | {bug.root_cause_category or 'N/A'} |
| **Regression Risk** | {bug.regression_risk or 'N/A'} |
| **Affected Users** | {bug.affected_users or 'N/A'} |

## Business Impact
{bug.business_impact or 'N/A'}

## Environment
{bug.environment_details}

## Steps to Reproduce
{chr(10).join([f'{i+1}. {s}' for i, s in enumerate(bug.steps_to_reproduce)])}

## Actual Result
{bug.actual_result}

## Expected Result
{bug.expected_result}

## Workaround
{bug.workaround or 'N/A'}

## Suggested Fix
{bug.suggested_fix or 'N/A'}

## Related Areas
{chr(10).join([f'- {a}' for a in (bug.related_areas or [])]) or 'N/A'}

## Screenshot Annotations
{chr(10).join([f'- {a}' for a in (bug.screenshot_annotations or [])]) or 'N/A'}

## JIRA Labels
{', '.join(bug.jira_labels or [])}
"""
        st.download_button(
            label="⬇️ Download JIRA Markdown",
            data=md_content.encode("utf-8"),
            file_name="bug_report.md",
            mime="text/markdown",
            key="bug_md_dl",
        )

    with d2:
        json_content = json.dumps(bug.model_dump(), indent=2)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_content.encode("utf-8"),
            file_name="bug_report.json",
            mime="application/json",
            key="bug_json_dl",
        )
