import streamlit as st
import pandas as pd
from langchain_core.output_parsers import PydanticOutputParser

from models import TestCaseList
from prompts import get_tc_prompt
from utils import (
    invoke_with_retry,
    get_category_badge_class,
    get_priority_badge_class,
    get_auto_feasibility_class,
    get_auto_effort_class,
    export_test_cases_to_excel,
)
from constants import CATEGORY_ORDER, PRIORITY_ORDER


def _sort_key(tc):
    """Sort test cases by category order, then priority, then ID."""
    cat_ord = CATEGORY_ORDER.get(tc.category, 99)
    prio_ord = PRIORITY_ORDER.get(tc.priority, 99)
    return (cat_ord, prio_ord, tc.id)


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Paste a User Story or Feature Requirement. '
        "The AI generates structured test cases with BDD scenarios, test data, "
        "traceability, and automation feasibility analysis.</div>",
        unsafe_allow_html=True,
    )

    user_story = st.text_area(
        "User Story / Feature Requirement",
        placeholder='e.g. "As a user, I want to log in with email and password. '
                    'The system should lock the account after 5 failed attempts."',
        height=120,
        key="tc_input",
    )

    tc_col1, tc_col2 = st.columns([2, 1])
    with tc_col1:
        coverage_focus = st.multiselect(
            "Test Coverage Focus",
            ["Functional", "Negative", "Boundary", "Edge Case", "Accessibility", "Security", "Performance", "Localization"],
            default=["Functional", "Negative", "Boundary", "Edge Case"],
            key="tc_coverage",
        )
    with tc_col2:
        tech_stack = st.text_input(
            "Tech Stack (optional)",
            placeholder="e.g. React frontend + Node.js + PostgreSQL",
            key="tc_stack",
        )

    tc_parser = PydanticOutputParser(pydantic_object=TestCaseList)

    if st.button("⚡ Generate Test Cases", key="tc_btn"):
        if not user_story.strip():
            st.warning("Please enter a user story or requirement.")
        else:
            with st.spinner("Analyzing requirements and architecting test suite..."):
                tc_prompt = get_tc_prompt()
                chain = tc_prompt | model | tc_parser
                full_input = (
                    f"User Story / Requirement:\n{user_story}\n\n"
                    f"Test Coverage Focus: {', '.join(coverage_focus)}\n"
                    f"Tech Stack: {tech_stack or 'Not provided'}"
                )
                try:
                    result = invoke_with_retry(chain, {
                        "user_story": full_input,
                        "format_instructions": tc_parser.get_format_instructions(),
                    })
                    st.session_state["tc_result"] = result
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "tc_result" not in st.session_state:
        return

    result = st.session_state["tc_result"]
    test_cases = sorted(result.test_cases, key=_sort_key)
    summary = result.summary

    st.markdown("---")
    st.markdown(
        f'<div class="section-title">📋 Generated {len(test_cases)} Test Cases</div>',
        unsafe_allow_html=True,
    )

    # ── Summary Dashboard ──────────────────────────────────────────────────
    high_prio_count = sum(1 for tc in test_cases if tc.priority.lower() == "high")
    auto_ready_count = sum(1 for tc in test_cases if tc.automation_feasibility.lower() == "high")
    smoke_count = sum(1 for tc in test_cases if any(t.lower() == "smoke" for t in tc.tags))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="stat-tile"><div class="num total-color">{summary.total_generated}</div>'
            f'<div class="lbl">Total Cases</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="stat-tile"><div class="num fail-color">{high_prio_count}</div>'
            f'<div class="lbl">High Priority</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="stat-tile"><div class="num pass-color">{auto_ready_count}</div>'
            f'<div class="lbl">Auto-Ready</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="stat-tile"><div class="num block-color">{smoke_count}</div>'
            f'<div class="lbl">Smoke Tests</div></div>',
            unsafe_allow_html=True,
        )

    # Category breakdown pills
    if summary.category_breakdown:
        pills = []
        for cb in summary.category_breakdown:
            badge_cls = get_category_badge_class(cb.category)
            pills.append(
                f'<span class="badge {badge_cls}">{cb.category}: {cb.count}</span>'
            )
        st.markdown(
            f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin:1rem 0;">{" ".join(pills)}</div>',
            unsafe_allow_html=True,
        )

    # Coverage gaps & recommendations
    if summary.coverage_gaps or summary.recommendations:
        gap_col, rec_col = st.columns(2)
        with gap_col:
            if summary.coverage_gaps:
                st.markdown(
                    '<div class="section-title">🔍 Coverage Gaps</div>',
                    unsafe_allow_html=True,
                )
                for gap in summary.coverage_gaps:
                    st.markdown(f"- {gap}")
        with rec_col:
            if summary.recommendations:
                st.markdown(
                    '<div class="section-title">💡 Recommendations</div>',
                    unsafe_allow_html=True,
                )
                for rec in summary.recommendations:
                    st.markdown(f"- {rec}")

    # Automation potential banner
    st.info(f"**Automation Coverage Potential:** {summary.automation_coverage_potential}")

    # ── Filters ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">🔧 Filters</div>',
        unsafe_allow_html=True,
    )

    all_categories = sorted(
        {tc.category for tc in test_cases},
        key=lambda x: CATEGORY_ORDER.get(x, 99),
    )
    all_priorities = ["High", "Medium", "Low"]
    all_feasibilities = sorted(
        {tc.automation_feasibility for tc in test_cases},
        key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(x, 99),
    )

    f_col1, f_col2, f_col3 = st.columns(3)
    with f_col1:
        sel_categories = st.multiselect(
            "Category",
            options=all_categories,
            default=all_categories,
            key="tc_filter_cat",
        )
    with f_col2:
        sel_priorities = st.multiselect(
            "Priority",
            options=all_priorities,
            default=all_priorities,
            key="tc_filter_prio",
        )
    with f_col3:
        sel_feasibility = st.multiselect(
            "Auto Feasibility",
            options=all_feasibilities,
            default=all_feasibilities,
            key="tc_filter_auto",
        )

    filtered = [
        tc for tc in test_cases
        if tc.category in sel_categories
        and tc.priority in sel_priorities
        and tc.automation_feasibility in sel_feasibility
    ]

    st.markdown(
        f"Showing **{len(filtered)}** of {len(test_cases)} test cases",
        unsafe_allow_html=True,
    )

    if not filtered:
        st.warning("No test cases match the selected filters.")
        return

    # ── Test Case Cards ────────────────────────────────────────────────────
    for tc in filtered:
        prio_class = get_priority_badge_class(tc.priority)
        cat_class = get_category_badge_class(tc.category)
        auto_class = get_auto_feasibility_class(tc.automation_feasibility)
        effort_class = get_auto_effort_class(tc.automation_effort)

        with st.expander(f"**{tc.id}** — {tc.title}", expanded=False):
            # Badge row
            st.markdown(
                f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.8rem;">'
                f'<span class="badge {prio_class}">{tc.priority}</span>'
                f'<span class="badge {cat_class}">{tc.category}</span>'
                f'<span class="badge {auto_class}">Auto: {tc.automation_feasibility}</span>'
                f'<span class="badge {effort_class}">Effort: {tc.automation_effort}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Traceability
            st.markdown(f"**🔗 Traceability:** _{tc.traceability}_")

            # Pre-conditions
            st.markdown("**Pre-conditions:**")
            st.markdown(
                f"<div style='padding-left:1rem;color:#94a3b8;margin-bottom:0.5rem;'>"
                f"{tc.pre_conditions}</div>",
                unsafe_allow_html=True,
            )

            # Steps
            st.markdown("**Steps:**")
            for i, step in enumerate(tc.steps, 1):
                st.markdown(
                    f"<div style='padding:0.15rem 0;padding-left:1rem;'>"
                    f"<span style='color:#3b82f6;font-family:Space Mono,monospace;margin-right:0.5rem;'>"
                    f"{i}.</span>{step}</div>",
                    unsafe_allow_html=True,
                )

            # Expected Result
            st.markdown("**Expected Result:**")
            st.markdown(
                f"<div style='padding-left:1rem;color:#34d399;margin-bottom:0.5rem;'>"
                f"{tc.expected_result}</div>",
                unsafe_allow_html=True,
            )

            # Test Data
            if tc.test_data:
                st.markdown("**Test Data:**")
                st.code(tc.test_data, language="text")

            # BDD Scenario
            if tc.bdd_scenario:
                st.markdown("**BDD Scenario:**")
                st.code(tc.bdd_scenario, language="gherkin")

            # Tags
            if tc.tags:
                tag_html = " ".join([
                    f'<span style="display:inline-block;padding:0.15rem 0.5rem;'
                    f'border-radius:4px;background:rgba(59,130,246,0.1);'
                    f'color:#60a5fa;font-size:0.75rem;margin-right:0.3rem;">#{t}</span>'
                    for t in tc.tags
                ])
                st.markdown(
                    f'<div style="margin-top:0.5rem;">{tag_html}</div>',
                    unsafe_allow_html=True,
                )

    # ── Exports ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    e_col1, e_col2 = st.columns(2)
    with e_col1:
        rows = []
        for tc in filtered:
            rows.append({
                "ID": tc.id,
                "Title": tc.title,
                "Category": tc.category,
                "Priority": tc.priority,
                "Pre-conditions": tc.pre_conditions,
                "Steps": "\n".join(f"{i+1}. {s}" for i, s in enumerate(tc.steps)),
                "Expected Result": tc.expected_result,
                "Test Data": tc.test_data or "",
                "BDD Scenario": tc.bdd_scenario or "",
                "Auto Feasibility": tc.automation_feasibility,
                "Auto Effort": tc.automation_effort,
                "Tags": ", ".join(tc.tags),
                "Traceability": tc.traceability,
            })
        df = pd.DataFrame(rows)
        csv_data = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_data,
            file_name="test_cases.csv",
            mime="text/csv",
            key="tc_csv_dl",
        )

    with e_col2:
        try:
            excel_data = export_test_cases_to_excel(result)
            st.download_button(
                label="⬇️ Download Excel (.xlsx)",
                data=excel_data,
                file_name="test_suite.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="tc_xlsx_dl",
            )
        except Exception as e:
            st.error(f"Excel export failed: {e}")
