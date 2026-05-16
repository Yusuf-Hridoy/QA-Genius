import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import PerformanceTestSuite
from prompts import get_performance_prompt
from utils import (
    invoke_with_retry,
    repair_llm_json,
    get_perf_framework_badge_class,
    get_load_profile_badge_class,
    get_criticality_badge_class,
    create_performance_zip,
)


def render(model):
    st.markdown(
        '<div class="tip-box">⚡ Describe your user flows, expected load, and SLA targets. '
        "The AI generates runnable performance test scripts with 6 load profiles, "
        "SLA assertions, and a Grafana dashboard config.</div>",
        unsafe_allow_html=True,
    )

    # ── Input Form ───────────────────────────────────────────────────────────
    user_flows = st.text_area(
        "User Flows & API Endpoints",
        placeholder='e.g. "1. POST /api/auth/login with email+password\n'
                    '2. GET /api/products/search?q=laptop\n'
                    '3. POST /api/cart/items with product_id\n'
                    '4. POST /api/checkout with Stripe token\n'
                    'Think time: 1-2s between steps"',
        height=120,
        key="perf_input_flows",
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        framework = st.selectbox(
            "Framework",
            ["k6"],
            key="perf_framework",
        )
    with c2:
        expected_users = st.text_input(
            "Expected Concurrent Users",
            placeholder="e.g. 5000",
            key="perf_users",
        )
    with c3:
        peak_event_type = st.selectbox(
            "Peak Event Type",
            ["Daily Peak", "Black Friday / Flash Sale", "Live Event Spike", "Cron Job Spike", "Marketing Campaign Launch", "Custom"],
            key="perf_peak_type",
        )
        if peak_event_type == "Custom":
            peak_event_custom = st.text_input(
                "Custom ramp shape description",
                placeholder="e.g. sharp 10x ramp over 30s, sustained 2h",
                key="perf_peak_custom",
            )
        else:
            peak_event_custom = ""

    sla_targets = st.text_area(
        "SLA Targets",
        placeholder='e.g. "p95 latency < 300ms\n'
                    'error rate < 0.5%\n'
                    'throughput > 1000 RPS\n'
                    'p99 latency < 600ms"',
        height=80,
        key="perf_sla",
    )

    endpoint_sla = st.text_area(
        "Per-endpoint SLAs (optional)",
        placeholder='One per line: endpoint | p95 target | p99 target (optional)\n'
                    'e.g.\n'
                    '/api/auth/login | 200ms | 500ms\n'
                    '/api/products | 300ms | 600ms\n'
                    '/api/checkout | 400ms | 800ms',
        height=80,
        key="perf_endpoint_sla",
    )

    output_config = st.multiselect(
        "Metrics Output",
        ["Console only", "InfluxDB + Grafana", "Prometheus remote write + Grafana", "k6 Cloud", "JSON file"],
        default=["InfluxDB + Grafana"],
        key="perf_output",
    )

    perf_parser = PydanticOutputParser(pydantic_object=PerformanceTestSuite)

    if st.button("⚡ Generate Performance Suite", key="perf_btn"):
        if not user_flows.strip():
            st.warning("Please describe your user flows.")
        else:
            with st.spinner("Architecting performance scenarios, load profiles, and generating runnable scripts..."):
                perf_prompt = get_performance_prompt()
                try:
                    # First get raw text from model, then strip markdown fences if present
                    peak_desc = peak_event_custom if peak_event_type == "Custom" else peak_event_type
                    raw_chain = perf_prompt | model
                    raw_text = invoke_with_retry(raw_chain, {
                        "user_flows": user_flows,
                        "framework": framework,
                        "expected_users": expected_users or "1000",
                        "peak_event_type": peak_desc,
                        "sla_targets": sla_targets or "p95 latency < 500ms, error rate < 1%",
                        "endpoint_slas": endpoint_sla.strip() if endpoint_sla.strip() else "None provided",
                        "output_config": ", ".join(output_config) if output_config else "Console only",
                        "format_instructions": perf_parser.get_format_instructions(),
                    })
                    if hasattr(raw_text, "content"):
                        raw_text = raw_text.content
                    cleaned = repair_llm_json(raw_text)
                    result = perf_parser.parse(cleaned)
                    st.session_state["perf_result"] = result
                except Exception as e:
                    st.error(f"Generation error: {e}")
                    return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "perf_result" not in st.session_state:
        return

    result = st.session_state["perf_result"]
    suite = result

    st.markdown("---")
    st.markdown(
        f'<div class="section-title">⚡ Performance Test Suite ({suite.framework})</div>',
        unsafe_allow_html=True,
    )

    # ── Summary Dashboard ────────────────────────────────────────────────────
    fw_class = get_perf_framework_badge_class(suite.framework)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f'<div class="stat-tile"><div class="num total-color">{len(suite.scenarios)}</div>'
            f'<div class="lbl">Scenarios</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="stat-tile"><div class="num pass-color">{len(suite.load_profiles)}</div>'
            f'<div class="lbl">Load Profiles</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="stat-tile"><div class="num block-color">{len(suite.sla_assertions)}</div>'
            f'<div class="lbl">SLA Assertions</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="stat-tile"><div class="num {fw_class}">{suite.framework}</div>'
            f'<div class="lbl">Framework</div></div>',
            unsafe_allow_html=True,
        )

    # Critical journeys
    if suite.critical_user_journeys:
        st.markdown(
            '<div class="section-title">🎯 Critical User Journeys</div>',
            unsafe_allow_html=True,
        )
        for journey in suite.critical_user_journeys:
            st.markdown(f"- {journey}")

    # ── Scenarios ────────────────────────────────────────────────────────────
    if suite.scenarios:
        st.markdown(
            '<div class="section-title">📋 Performance Scenarios</div>',
            unsafe_allow_html=True,
        )
        for sc in suite.scenarios:
            crit_class = get_criticality_badge_class(sc.criticality)
            with st.expander(f"**{sc.id}** — {sc.name}", expanded=False):
                st.markdown(
                    f'<span class="badge {crit_class}">{sc.criticality}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Description:** {sc.description}")
                if sc.user_flow_steps:
                    st.markdown("**Flow Steps:**")
                    for i, step in enumerate(sc.user_flow_steps, 1):
                        st.markdown(f"{i}. {step}")
                if sc.api_endpoints:
                    st.markdown("**API Endpoints:**")
                    for ep in sc.api_endpoints:
                        st.code(ep, language="text")
                if sc.data_requirements:
                    st.markdown(f"**Data Requirements:** {sc.data_requirements}")

    # ── Load Profiles ────────────────────────────────────────────────────────
    if suite.load_profiles:
        st.markdown(
            '<div class="section-title">🔥 Load Profiles</div>',
            unsafe_allow_html=True,
        )
        for lp in suite.load_profiles:
            prof_class = get_load_profile_badge_class(lp.profile_type)
            with st.expander(
                f"**{lp.profile_type}** — Peak: {lp.peak_vus} VUs | Duration: {lp.duration}",
                expanded=False,
            ):
                st.markdown(
                    f'<span class="badge {prof_class}">{lp.profile_type}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Description:** {lp.description}")
                st.markdown(f"**Ramp Up:** {lp.ramp_up}")
                st.markdown(f"**Plateau:** {lp.plateau}")
                st.markdown(f"**Ramp Down:** {lp.ramp_down}")
                if lp.target_tps:
                    st.markdown(f"**Target TPS:** {lp.target_tps}")

    # ── SLA Assertions ───────────────────────────────────────────────────────
    if suite.sla_assertions:
        st.markdown(
            '<div class="section-title">📊 SLA Assertions</div>',
            unsafe_allow_html=True,
        )
        sla_data = []
        for sla in suite.sla_assertions:
            sev_class = get_criticality_badge_class(sla.severity)
            sla_data.append({
                "Metric": sla.metric,
                "Rule": f"{sla.operator} {sla.threshold}",
                "Severity": sla.severity,
            })
            st.markdown(
                f'<div style="display:flex;gap:0.75rem;align-items:center;margin:0.3rem 0;">'
                f'<span style="font-family:Space Mono,monospace;color:#60a5fa;">{sla.metric}</span>'
                f'<span style="color:#f87171;font-weight:600;">{sla.operator} {sla.threshold}</span>'
                f'<span class="badge {sev_class}">{sla.severity}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── Script Preview ───────────────────────────────────────────────────────
    st.markdown(
        '<div class="section-title">📝 Generated Script</div>',
        unsafe_allow_html=True,
    )
    lang_map = {"k6": "javascript", "jmeter": "xml", "artillery": "yaml"}
    st.code(suite.script_code, language=lang_map.get(suite.framework.lower(), "text"))

    if suite.sample_csv:
        st.markdown(
            '<div class="section-title">📄 Sample users.csv</div>',
            unsafe_allow_html=True,
        )
        st.code(suite.sample_csv, language="csv")

    if suite.grafana_dashboard:
        st.markdown(
            '<div class="section-title">📊 Grafana Dashboard</div>',
            unsafe_allow_html=True,
        )
        with st.expander("View Grafana dashboard JSON / reference", expanded=False):
            st.code(suite.grafana_dashboard, language="json")

    # ── Execution Plan ───────────────────────────────────────────────────────
    if suite.execution_plan:
        st.markdown(
            '<div class="section-title">📋 Execution Plan</div>',
            unsafe_allow_html=True,
        )
        for i, step in enumerate(suite.execution_plan, 1):
            st.markdown(f"{i}. {step}")

    # ── Design Notes ─────────────────────────────────────────────────────────
    if suite.design_notes:
        st.markdown(
            '<div class="section-title">💡 Design Notes</div>',
            unsafe_allow_html=True,
        )
        st.info(suite.design_notes)

    # ── Exports ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    e_col1, e_col2, e_col3, e_col4 = st.columns(4)

    with e_col1:
        st.download_button(
            label=f"⬇️ {suite.script_file_name}",
            data=suite.script_code.encode("utf-8"),
            file_name=suite.script_file_name,
            mime="text/plain",
            key="perf_script_dl",
        )

    with e_col2:
        plan_md = f"# Performance Test Execution Plan\n\n**Framework:** {suite.framework}\n**Run Command:** `{suite.run_command}`\n\n## Setup\n\n"
        for cmd in suite.setup_instructions:
            plan_md += f"```bash\n{cmd}\n```\n"
        plan_md += "\n## Execution Plan\n\n"
        for step in suite.execution_plan:
            plan_md += f"- {step}\n"
        if suite.design_notes:
            plan_md += f"\n## Design Notes\n\n{suite.design_notes}\n"
        st.download_button(
            label="⬇️ Execution Plan (.md)",
            data=plan_md.encode("utf-8"),
            file_name="execution-plan.md",
            mime="text/markdown",
            key="perf_plan_dl",
        )

    with e_col3:
        if suite.grafana_dashboard:
            st.download_button(
                label="⬇️ Grafana Dashboard (.json)",
                data=suite.grafana_dashboard.encode("utf-8"),
                file_name="grafana-dashboard.json",
                mime="application/json",
                key="perf_grafana_dl",
            )

    with e_col4:
        try:
            zip_data = create_performance_zip(suite)
            st.download_button(
                label="⬇️ Full Suite (.zip)",
                data=zip_data,
                file_name="performance-test-suite.zip",
                mime="application/zip",
                key="perf_zip_dl",
            )
        except Exception as e:
            st.error(f"ZIP export failed: {e}")
