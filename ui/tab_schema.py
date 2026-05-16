import json

import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import SchemaValidationReport
from prompts import get_sv_prompt
from constants import SEVERITY_ORDER
from utils import (
    invoke_with_retry,
    get_compliance_score_class,
    get_issue_type_badge_class,
)


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Paste a raw API response (JSON) and optionally describe what the schema should look like. '
        "The AI performs structural, semantic, and security validation with compliance scoring.</div>",
        unsafe_allow_html=True,
    )

    col_l, col_r = st.columns(2)
    with col_l:
        raw_json = st.text_area(
            "API Response (JSON)",
            placeholder='{\n  "user_id": 123,\n  "email": null,\n  "role": "admin",\n  "created_at": "2024-01-15"\n}',
            height=140,
            key="json_input",
        )
    with col_r:
        schema_desc = st.text_area(
            "Expected Schema Description (optional)",
            placeholder='e.g. "user_id must be integer, email must be non-null string, '
                        'role must be one of [user, admin], created_at must be ISO date, '
                        'profile_picture field should exist"',
            height=140,
            key="schema_input",
        )

    validation_layers = st.multiselect(
        "Validation Layers",
        ["Structural (types, formats)", "Semantic (business rules)", "Security (sensitive data, PII)"],
        default=["Structural (types, formats)", "Semantic (business rules)", "Security (sensitive data, PII)"],
        key="sv_layers",
    )

    c1, c2 = st.columns([1, 5])
    with c1:
        validate_clicked = st.button("🔍 Validate Schema", key="sv_btn", use_container_width=True)
    with c2:
        if st.button("✨ Format JSON", key="fmt_json_btn"):
            if raw_json.strip():
                try:
                    formatted = json.dumps(json.loads(raw_json), indent=2)
                    st.session_state["json_input"] = formatted
                    st.rerun()
                except json.JSONDecodeError:
                    st.toast("Invalid JSON — cannot format", icon="❌")
            else:
                st.toast("Nothing to format", icon="⚠️")

    sv_parser = PydanticOutputParser(pydantic_object=SchemaValidationReport)

    if validate_clicked:
        if not raw_json.strip():
            st.warning("Please paste an API response to validate.")
        else:
            try:
                parsed_json = json.loads(raw_json)
            except json.JSONDecodeError as je:
                st.error(f"❌ Invalid JSON syntax: {je}")
                st.stop()

            with st.spinner("Performing structural, semantic, and security analysis..."):
                sv_prompt = get_sv_prompt()
                chain = sv_prompt | model | sv_parser
                try:
                    report = invoke_with_retry(chain, {
                        "json_payload": json.dumps(parsed_json, indent=2),
                        "schema_desc": schema_desc.strip() if schema_desc.strip() else "No schema provided — validate using REST API best practices.",
                        "validation_layers": ", ".join(validation_layers) if validation_layers else "None selected",
                        "format_instructions": sv_parser.get_format_instructions(),
                    })
                    st.session_state["sv_result"] = report
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "sv_result" not in st.session_state:
        return

    report = st.session_state["sv_result"]

    st.markdown("---")
    st.markdown(
        '<div class="section-title">🔍 Schema Validation Report</div>',
        unsafe_allow_html=True,
    )

    # ── Executive Dashboard ────────────────────────────────────────────────
    status = report.overall_status.upper()
    if status == "PASS":
        status_badge, status_card = "badge-pass", "glass-card-green"
    elif status == "WARN":
        status_badge, status_card = "badge-warn", "glass-card-yellow"
    else:
        status_badge, status_card = "badge-fail", "glass-card-red"

    score_class = get_compliance_score_class(report.compliance_score)

    dash_col1, dash_col2 = st.columns([1, 2])
    with dash_col1:
        st.markdown(
            f'<div class="glass-card" style="text-align:center;padding:2rem 1rem;">'
            f'<div class="label" style="text-align:center;">Compliance Score</div>'
            f'<div class="score-num {score_class}">{report.compliance_score}</div>'
            f'<div style="margin-top:0.8rem;"><span class="badge {status_badge}">{status}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with dash_col2:
        st.markdown(
            f'<div class="glass-card {status_card}">'
            f'<div style="display:flex;align-items:center;gap:1rem;">'
            f'<span class="badge {status_badge}" style="font-size:0.85rem;padding:0.3rem 1rem;">{status}</span>'
            f'<div><div style="font-family:Space Mono,monospace;font-size:0.7rem;color:#475569;'
            f'text-transform:uppercase;letter-spacing:0.1em;">Validation Result</div>'
            f'<div style="color:#e2e8f0;font-size:0.92rem;margin-top:0.2rem;">{report.overall_recommendation}</div></div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        if report.score_breakdown:
            st.markdown(
                f'<div class="glass-card" style="margin-top:0.8rem;">'
                f'<div style="font-family:Space Mono,monospace;font-size:0.7rem;color:#475569;'
                f'text-transform:uppercase;letter-spacing:0.1em;">Score Breakdown</div>'
                f'<div style="color:#e2e8f0;font-size:0.85rem;margin-top:0.3rem;white-space:pre-wrap;">{report.score_breakdown}</div></div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.8rem;margin-top:0.8rem;">'
            f'<div class="stat-tile"><div class="num total-color">{report.total_checks}</div><div class="lbl">Total Checks</div></div>'
            f'<div class="stat-tile"><div class="num pass-color">{report.passed_checks}</div><div class="lbl">Passed</div></div>'
            f'<div class="stat-tile"><div class="num fail-color">{report.failed_checks}</div><div class="lbl">Failed</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Missing / Extra / Security / Semantic ──────────────────────────────
    if report.missing_fields or report.extra_fields:
        st.markdown("---")
        me_col1, me_col2 = st.columns(2)
        with me_col1:
            if report.missing_fields:
                missing_html = " ".join([
                    f'<span style="display:inline-block;padding:0.2rem 0.5rem;border-radius:4px;'
                    f'background:rgba(248,113,113,0.1);color:#f87171;font-size:0.78rem;'
                    f'font-family:Space Mono,monospace;margin:0.15rem;">⚠ {f}</span>'
                    for f in report.missing_fields
                ])
                st.markdown(
                    f'<div class="glass-card glass-card-red">'
                    f'<div class="label" style="color:#f87171;">Missing Required Fields</div>'
                    f'<div style="margin-top:0.5rem;">{missing_html}</div></div>',
                    unsafe_allow_html=True,
                )
        with me_col2:
            if report.extra_fields:
                extra_html = " ".join([
                    f'<span style="display:inline-block;padding:0.2rem 0.5rem;border-radius:4px;'
                    f'background:rgba(251,191,36,0.1);color:#fbbf24;font-size:0.78rem;'
                    f'font-family:Space Mono,monospace;margin:0.15rem;">+ {f}</span>'
                    for f in report.extra_fields
                ])
                st.markdown(
                    f'<div class="glass-card glass-card-yellow">'
                    f'<div class="label" style="color:#fbbf24;">Extra / Unexpected Fields</div>'
                    f'<div style="margin-top:0.5rem;">{extra_html}</div></div>',
                    unsafe_allow_html=True,
                )

    if report.security_concerns:
        st.markdown("---")
        sec_html = "".join([
            f'<div style="padding:0.4rem 0;border-bottom:1px solid #1a2535;">'
            f'<span style="color:#ef4444;margin-right:0.5rem;">🔒</span>'
            f'<span style="color:#e2e8f0;font-size:0.9rem;">{sc}</span></div>'
            for sc in report.security_concerns
        ])
        st.markdown(
            f'<div class="glass-card glass-card-red">'
            f'<div class="label" style="color:#ef4444;">🔒 Security Concerns</div>'
            f'<div style="margin-top:0.5rem;">{sec_html}</div></div>',
            unsafe_allow_html=True,
        )

    if report.semantic_issues:
        st.markdown("---")
        sem_html = "".join([
            f'<div style="padding:0.4rem 0;border-bottom:1px solid #1a2535;">'
            f'<span style="color:#fbbf24;margin-right:0.5rem;">📐</span>'
            f'<span style="color:#e2e8f0;font-size:0.9rem;">{si}</span></div>'
            for si in report.semantic_issues
        ])
        st.markdown(
            f'<div class="glass-card glass-card-yellow">'
            f'<div class="label" style="color:#fbbf24;">📐 Semantic Issues</div>'
            f'<div style="margin-top:0.5rem;">{sem_html}</div></div>',
            unsafe_allow_html=True,
        )

    # ── Schema Summary ─────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        f'<div class="glass-card">'
        f'<div class="label">🗂️ Detected Schema Structure</div>'
        f'<div class="value">{report.schema_summary}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Issues List ────────────────────────────────────────────────────────
    if report.issues:
        st.markdown("---")
        st.markdown(
            f'<div class="section-title">⚠️ {len(report.issues)} Issue(s) Found</div>',
            unsafe_allow_html=True,
        )

        sorted_issues = sorted(report.issues, key=lambda x: SEVERITY_ORDER.get(x.severity, 9))

        for issue in sorted_issues:
            sev = issue.severity.lower()
            icon = "🔴" if sev == "critical" else ("🟠" if sev == "high" else ("🟡" if sev == "medium" else "🟢"))
            badge_cls = f"badge-{sev}" if sev in ["critical", "high", "medium", "low"] else "badge-medium"
            type_cls = get_issue_type_badge_class(issue.issue_type)
            itype = issue.issue_type.replace("_", " ").title()
            path_display = issue.path if issue.path and issue.path != "root" else issue.field

            with st.expander(f"{icon} {path_display} — {itype}", expanded=False):
                st.markdown(
                    f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.8rem;">'
                    f'<span class="badge {badge_cls}">{issue.severity}</span>'
                    f'<span class="badge {type_cls}">{itype}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                st.markdown(f"**Field:** `{issue.field}`")
                if issue.path and issue.path != "root":
                    st.markdown(f"**Path:** `{issue.path}`")
                st.markdown(f"**Description:** {issue.description}")

                if issue.expected_type or issue.actual_value:
                    exp = issue.expected_type or "N/A"
                    act = issue.actual_value or "N/A"
                    st.markdown(
                        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:0.8rem;margin:0.8rem 0;">'
                        f'<div style="background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.15);'
                        f'border-radius:8px;padding:0.6rem;">'
                        f'<div style="font-size:0.65rem;color:#34d399;text-transform:uppercase;letter-spacing:0.1em;">Expected</div>'
                        f'<div style="font-family:Space Mono,monospace;font-size:0.82rem;color:#e2e8f0;margin-top:0.3rem;">{exp}</div></div>'
                        f'<div style="background:rgba(248,113,113,0.05);border:1px solid rgba(248,113,113,0.15);'
                        f'border-radius:8px;padding:0.6rem;">'
                        f'<div style="font-size:0.65rem;color:#f87171;text-transform:uppercase;letter-spacing:0.1em;">Actual</div>'
                        f'<div style="font-family:Space Mono,monospace;font-size:0.82rem;color:#e2e8f0;margin-top:0.3rem;">{act}</div></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                if issue.constraint_violated:
                    st.markdown(
                        f'<div style="background:rgba(251,191,36,0.05);border:1px solid rgba(251,191,36,0.15);'
                        f'border-radius:8px;padding:0.6rem;margin-bottom:0.8rem;">'
                        f'<div style="font-size:0.65rem;color:#fbbf24;text-transform:uppercase;letter-spacing:0.1em;">'
                        f'Constraint Violated</div>'
                        f'<div style="font-family:Space Mono,monospace;font-size:0.82rem;color:#e2e8f0;margin-top:0.3rem;">'
                        f'{issue.constraint_violated}</div></div>',
                        unsafe_allow_html=True,
                    )

                st.markdown(f"**💡 Suggestion:** {issue.suggestion}")
    else:
        st.success("✅ No issues found — schema looks clean!")

    # ── Exports ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    d1, d2 = st.columns(2)
    with d1:
        md_content = f"""# Schema Validation Report

## Summary
| Metric | Value |
|--------|-------|
| **Overall Status** | {report.overall_status} |
| **Compliance Score** | {report.compliance_score}/100 |
| **Total Checks** | {report.total_checks} |
| **Passed** | {report.passed_checks} |
| **Failed** | {report.failed_checks} |

## Schema Summary
{report.schema_summary}

## Recommendation
{report.overall_recommendation}

## Missing Fields
{chr(10).join([f'- {f}' for f in (report.missing_fields or [])]) or 'None'}

## Extra Fields
{chr(10).join([f'- {f}' for f in (report.extra_fields or [])]) or 'None'}

## Security Concerns
{chr(10).join([f'- {sc}' for sc in (report.security_concerns or [])]) or 'None'}

## Semantic Issues
{chr(10).join([f'- {si}' for si in (report.semantic_issues or [])]) or 'None'}

## Detailed Issues
{chr(10).join([
    f'### {i+1}. {issue.field} ({issue.issue_type})\n'
    f'- **Path:** {issue.path or "root"}\n'
    f'- **Severity:** {issue.severity}\n'
    f'- **Description:** {issue.description}\n'
    f'- **Expected:** {issue.expected_type or "N/A"}\n'
    f'- **Actual:** {issue.actual_value or "N/A"}\n'
    f'- **Constraint:** {issue.constraint_violated or "N/A"}\n'
    f'- **Suggestion:** {issue.suggestion}'
    for i, issue in enumerate(report.issues)
])}
"""
        st.download_button(
            label="⬇️ Download Markdown Report",
            data=md_content.encode("utf-8"),
            file_name="schema_validation_report.md",
            mime="text/markdown",
            key="sv_md_dl",
        )

    with d2:
        report_dict = {
            "overall_status": report.overall_status,
            "compliance_score": report.compliance_score,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "schema_summary": report.schema_summary,
            "overall_recommendation": report.overall_recommendation,
            "missing_fields": report.missing_fields or [],
            "extra_fields": report.extra_fields or [],
            "security_concerns": report.security_concerns or [],
            "semantic_issues": report.semantic_issues or [],
            "issues": [i.model_dump() for i in report.issues]
        }
        st.download_button(
            label="⬇️ Download JSON",
            data=json.dumps(report_dict, indent=2).encode("utf-8"),
            file_name="schema_validation_report.json",
            mime="application/json",
            key="sv_json_dl",
        )
