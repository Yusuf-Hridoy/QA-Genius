import streamlit as st
import pandas as pd
from langchain_core.output_parsers import PydanticOutputParser

from models import SecurityReport
from prompts import get_security_prompt
from utils import (
    invoke_with_retry,
    repair_llm_json,
    get_test_type_badge_class,
    get_owasp_status_badge_class,
    get_risk_level_badge_class,
    get_security_score_class,
    export_security_to_excel,
)
from constants import OWASP_SEVERITY_ORDER


def _sort_key(tc):
    """Sort by severity (Critical first), then OWASP ID, then test ID."""
    sev_ord = OWASP_SEVERITY_ORDER.get(tc.severity, 99)
    return (sev_ord, tc.owasp_id, tc.id)


def render(model):
    st.markdown(
        '<div class="tip-box">🔐 Describe your application, tech stack, and auth mechanism. '
        "The AI generates OWASP Top 10-based security test cases with real payloads, "
        "remediation guidance, and tool hints.</div>",
        unsafe_allow_html=True,
    )

    # ── Input Form ───────────────────────────────────────────────────────────
    app_desc = st.text_area(
        "Application Description",
        placeholder='e.g. "E-commerce platform with React frontend, Node.js + Express API, '
                    'MongoDB database, JWT authentication, Stripe payments, file upload for '
                    'product images, admin dashboard for inventory management."',
        height=100,
        key="sec_input_desc",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        app_type = st.selectbox(
            "Application Type",
            ["Web Application", "API / Microservices", "Mobile App", "Desktop App", "Hybrid"],
            key="sec_app_type",
        )
    with c2:
        auth_type = st.selectbox(
            "Authentication",
            ["JWT / OAuth2", "Session Cookies", "API Keys", "Basic Auth", "SSO / SAML", "None / Public"],
            key="sec_auth_type",
        )
    with c3:
        sensitive_features = st.multiselect(
            "Sensitive Features",
            ["Payments", "File Upload", "User Data / PII", "Admin Panel", "Public API", "Chat / Messaging", "Search"],
            default=["Payments", "User Data / PII"],
            key="sec_features",
        )

    sec_parser = PydanticOutputParser(pydantic_object=SecurityReport)

    if st.button("🔒 Generate Security Tests", key="sec_btn"):
        if not app_desc.strip():
            st.warning("Please enter an application description.")
        else:
            full_context = (
                f"Application Type: {app_type}\n"
                f"Authentication: {auth_type}\n"
                f"Sensitive Features: {', '.join(sensitive_features)}\n\n"
                f"Description:\n{app_desc}"
            )
            with st.spinner("Performing threat modeling and generating OWASP-mapped security tests..."):
                sec_prompt = get_security_prompt()
                try:
                    raw_chain = sec_prompt | model
                    raw_text = invoke_with_retry(raw_chain, {
                        "app_desc": full_context,
                        "format_instructions": sec_parser.get_format_instructions(),
                    })
                    if hasattr(raw_text, "content"):
                        raw_text = raw_text.content
                    cleaned = repair_llm_json(raw_text)
                    result = sec_parser.parse(cleaned)
                    st.session_state["sec_result"] = result
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "sec_result" not in st.session_state:
        return

    result = st.session_state["sec_result"]
    test_cases = sorted(result.test_cases, key=_sort_key)
    summary = result.summary

    st.markdown("---")
    st.markdown(
        f'<div class="section-title">🛡️ Generated {len(test_cases)} Security Tests</div>',
        unsafe_allow_html=True,
    )

    # ── Summary Dashboard ────────────────────────────────────────────────────
    crit_count = summary.critical_count
    high_count = summary.high_count
    cov_score = summary.coverage_score

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="stat-tile"><div class="num total-color">{summary.total_tests}</div>'
            f'<div class="lbl">Total Tests</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="stat-tile"><div class="num fail-color">{crit_count}</div>'
            f'<div class="lbl">Critical</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="stat-tile"><div class="num block-color">{high_count}</div>'
            f'<div class="lbl">High Severity</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        score_class = get_security_score_class(cov_score)
        st.markdown(
            f'<div class="stat-tile"><div class="num {score_class}">{cov_score}%</div>'
            f'<div class="lbl">OWASP Coverage</div></div>',
            unsafe_allow_html=True,
        )

    # Risk level banner
    risk_class = get_risk_level_badge_class(summary.overall_risk)
    st.markdown(
        f'<div style="margin:1rem 0;display:flex;align-items:center;gap:0.75rem;">'
        f'<span style="font-size:0.95rem;color:#94a3b8;">Overall Risk Level:</span>'
        f'<span class="badge {risk_class}">{summary.overall_risk.upper()}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # OWASP coverage matrix
    if summary.owasp_coverage:
        st.markdown(
            '<div class="section-title">📊 OWASP Top 10 Coverage</div>',
            unsafe_allow_html=True,
        )
        cov_pills = []
        for cov in summary.owasp_coverage:
            badge_cls = get_owasp_status_badge_class(cov.status)
            cov_pills.append(
                f'<span class="badge {badge_cls}">{cov.owasp_id} {cov.category}: {cov.test_count} ({cov.status})</span>'
            )
        st.markdown(
            f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin:0.5rem 0;">{" ".join(cov_pills)}</div>',
            unsafe_allow_html=True,
        )

    # Key findings & recommendations
    if summary.key_findings or summary.recommendations:
        find_col, rec_col = st.columns(2)
        with find_col:
            if summary.key_findings:
                st.markdown(
                    '<div class="section-title">🔍 Key Findings</div>',
                    unsafe_allow_html=True,
                )
                for finding in summary.key_findings:
                    st.markdown(f"- {finding}")
        with rec_col:
            if summary.recommendations:
                st.markdown(
                    '<div class="section-title">💡 Recommendations</div>',
                    unsafe_allow_html=True,
                )
                for rec in summary.recommendations:
                    st.markdown(f"- {rec}")

    # ── Filters ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">🔧 Filters</div>',
        unsafe_allow_html=True,
    )

    all_owasp = sorted({tc.owasp_category for tc in test_cases})
    all_severities = ["Critical", "High", "Medium", "Low"]
    all_types = sorted({tc.test_type for tc in test_cases})

    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        sel_owasp = st.multiselect(
            "OWASP Category",
            options=all_owasp,
            default=all_owasp,
            key="sec_filter_cat",
        )
    with f_col2:
        sel_severities = st.multiselect(
            "Severity",
            options=all_severities,
            default=all_severities,
            key="sec_filter_sev",
        )
    with f_col3:
        sel_types = st.multiselect(
            "Test Type",
            options=all_types,
            default=all_types,
            key="sec_filter_type",
        )

    filtered = [
        tc for tc in test_cases
        if tc.owasp_category in sel_owasp
        and tc.severity in sel_severities
        and tc.test_type in sel_types
    ]

    st.markdown(
        f"Showing **{len(filtered)}** of {len(test_cases)} security tests",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.warning("No security tests match the selected filters.")
        return

    # ── Security Test Cards ──────────────────────────────────────────────────
    for tc in filtered:
        sev_class = get_risk_level_badge_class(tc.severity)
        type_class = get_test_type_badge_class(tc.test_type)

        with st.expander(f"**{tc.id}** — {tc.title}", expanded=False):
            # Badge row
            st.markdown(
                f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.8rem;">'
                f'<span class="badge {sev_class}">{tc.severity}</span>'
                f'<span class="badge {type_class}">{tc.test_type}</span>'
                f'<span style="display:inline-block;padding:0.15rem 0.5rem;border-radius:4px;'
                f'background:rgba(147,51,234,0.15);color:#c084fc;font-size:0.8rem;">'
                f'{tc.owasp_id} {tc.owasp_category}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Description
            st.markdown("**Description:**")
            st.markdown(
                f"<div style='padding-left:1rem;color:#cbd5e1;margin-bottom:0.5rem;'>"
                f"{tc.description}</div>",
                unsafe_allow_html=True,
            )

            # Steps
            st.markdown("**Steps:**")
            for i, step in enumerate(tc.steps, 1):
                st.markdown(
                    f"<div style='padding:0.15rem 0;padding-left:1rem;'>"
                    f"<span style='color:#f87171;font-family:Space Mono,monospace;margin-right:0.5rem;'>"
                    f"{i}.</span>{step}</div>",
                    unsafe_allow_html=True,
                )

            # Sample Payloads
            if tc.sample_payloads:
                st.markdown("**Sample Payloads:**")
                for payload in tc.sample_payloads:
                    st.code(payload, language="text")

            # Remediation
            st.markdown("**Remediation:**")
            st.markdown(
                f"<div style='padding-left:1rem;color:#34d399;margin-bottom:0.5rem;'>"
                f"{tc.remediation}</div>",
                unsafe_allow_html=True,
            )

            # Tool Hint
            if tc.tool_hint:
                st.markdown(
                    f'<div style="margin-top:0.5rem;padding:0.5rem;border-radius:6px;'
                    f'background:rgba(59,130,246,0.08);border-left:3px solid #3b82f6;">'
                    f'<span style="color:#60a5fa;font-weight:600;">🛠️ Tool Hint:</span> '
                    f'<span style="color:#94a3b8;">{tc.tool_hint}</span></div>',
                    unsafe_allow_html=True,
                )

    # ── Exports ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    e_col1, e_col2, e_col3 = st.columns(3)

    with e_col1:
        rows = []
        for tc in filtered:
            rows.append({
                "ID": tc.id,
                "OWASP ID": tc.owasp_id,
                "Category": tc.owasp_category,
                "Title": tc.title,
                "Description": tc.description,
                "Steps": "\n".join(f"{i+1}. {s}" for i, s in enumerate(tc.steps)),
                "Sample Payloads": "\n".join(f"• {p}" for p in tc.sample_payloads),
                "Severity": tc.severity,
                "Remediation": tc.remediation,
                "Tool Hint": tc.tool_hint,
                "Test Type": tc.test_type,
            })
        df = pd.DataFrame(rows)
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name="security_tests.csv",
            mime="text/csv",
            key="sec_csv_dl",
        )

    with e_col2:
        try:
            excel_data = export_security_to_excel(result)
            st.download_button(
                label="⬇️ Download Excel (.xlsx)",
                data=excel_data,
                file_name="security_test_suite.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="sec_xlsx_dl",
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")

    with e_col3:
        # Payload library JSON export
        payload_rows = []
        for tc in filtered:
            for payload in tc.sample_payloads:
                payload_rows.append({
                    "test_id": tc.id,
                    "owasp_id": tc.owasp_id,
                    "category": tc.owasp_category,
                    "severity": tc.severity,
                    "payload": payload,
                })
        if payload_rows:
            payload_df = pd.DataFrame(payload_rows)
            payload_json = payload_df.to_json(orient="records", indent=2).encode("utf-8")
            st.download_button(
                label="⬇️ Payload Library (JSON)",
                data=payload_json,
                file_name="payload_library.json",
                mime="application/json",
                key="sec_payload_dl",
            )
