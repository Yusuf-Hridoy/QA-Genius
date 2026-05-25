import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import AutomationScript
from prompts import get_auto_prompt
from utils import (
    invoke_with_retry,
    parse_llm_response,
    show_error_actions,
    create_automation_zip,
)
from validators import validate_text_input, detect_suspicious_content, ValidationError


def _lang_from_framework(framework: str, explicit_lang: str = "") -> str:
    """Determine code block language from framework name and explicit language choice."""
    if "Python" in framework:
        return "python"
    if explicit_lang == "JavaScript":
        return "javascript"
    if explicit_lang == "TypeScript" or "JavaScript" in framework or "TypeScript" in framework:
        return "typescript"
    return "python"


def _build_tree_html(structure: list[str]) -> str:
    """Convert a list of file paths into a styled tree HTML."""
    lines = []
    for path in structure:
        depth = path.count("/")
        indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * depth
        name = path.split("/")[-1] if "/" in path else path
        folder = path.count("/") > 0 and not path.endswith((".py", ".js", ".ts", ".json", ".txt", ".ini", ".cfg", ".md"))
        icon = "📁" if folder else "📄"
        lines.append(
            f'<div style="font-family:Space Mono,monospace;font-size:0.82rem;'
            f'padding:0.15rem 0;color:#cbd5e1;">{indent}{icon} {name}</div>'
        )
    return "".join(lines)


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Describe a test scenario and choose your framework. '
        "The AI generates a complete, production-ready automation project with Page Objects, "
        "fixtures, config, and setup instructions.</div>",
        unsafe_allow_html=True,
    )

    col_i, col_f = st.columns([3, 1])
    with col_i:
        scenario_desc = st.text_area(
            "Test Scenario Description",
            placeholder='e.g. "Login test for an e-commerce site: valid login, invalid password, '
                        'empty fields, account lockout after 5 attempts."',
            height=120,
            key="auto_input",
        )
    with col_f:
        framework_choice = st.selectbox(
            "Framework",
            options=[
                "Playwright (Python)",
                "Playwright (JavaScript)",
                "Selenium (Python)",
                "Cypress (JavaScript)",
            ],
            key="framework_select",
        )

    opts_col1, opts_col2, opts_col3, opts_col4 = st.columns(4)
    with opts_col1:
        language_choice = st.radio(
            "Language",
            ["JavaScript", "TypeScript"],
            index=0,
            key="auto_lang",
        )
    with opts_col2:
        structure_choice = st.radio(
            "Structure",
            ["Flat scripts (no POM)", "Page Object Model"],
            index=0,
            key="auto_struct",
        )
    with opts_col3:
        browser_choice = st.multiselect(
            "Browsers",
            ["Chromium", "Firefox", "WebKit"],
            default=["Chromium"],
            key="auto_browsers",
        )
    with opts_col4:
        site_type = st.selectbox(
            "Target Site Type",
            [
                "Custom (paste URL above)",
                "saucedemo.com",
                "the-internet.herokuapp.com",
                "automationexercise.com",
            ],
            key="auto_site",
        )

    auto_parser = PydanticOutputParser(pydantic_object=AutomationScript)

    if st.button("⚙️ Generate Project", key="auto_btn"):
        try:
            validated_scenario = validate_text_input(
                scenario_desc, "Test Scenario Description", min_chars=30, max_chars=5000
            )
            is_suspicious, msg = detect_suspicious_content(validated_scenario)
            if is_suspicious:
                st.warning(msg + " Please rephrase as a normal QA request.")
                return
        except ValidationError as e:
            st.error(str(e))
            return

        with st.spinner("Architecting automation project..."):
            auto_prompt = get_auto_prompt()
            raw_chain = auto_prompt | model
            try:
                raw = invoke_with_retry(raw_chain, {
                    "scenario": validated_scenario,
                    "framework": framework_choice,
                    "language": language_choice,
                    "structure": structure_choice,
                    "browsers": ", ".join(browser_choice) if browser_choice else "Chromium",
                    "site_type": site_type,
                    "format_instructions": auto_parser.get_format_instructions(),
                })
                if hasattr(raw, "content"):
                    raw = raw.content
                script = parse_llm_response(raw, AutomationScript, tab_name="Automation Script")
                if script is None:
                    show_error_actions("Automation Script")
                    return
                st.session_state["auto_result"] = script
            except Exception as e:
                st.error(f"Generation error: {e}")
                show_error_actions("Automation Script", str(e))
                return


    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "auto_result" not in st.session_state:
        return

    script = st.session_state["auto_result"]

    try:
        _render_auto_results(script)
    except Exception as e:
        st.error(
            "The AI response was generated successfully, but couldn't be displayed in the standard view. "
            "Showing the raw response below."
        )
        with st.expander("Raw Response (for debugging)", expanded=False):
            try:
                st.json(script.model_dump())
            except Exception:
                st.code(str(script))
        show_error_actions("Automation Script", str(e))


def _render_auto_results(script):
    """Render automation script results."""
    explicit_lang = st.session_state.get("auto_lang", "")
    lang = _lang_from_framework(script.framework, explicit_lang)

    st.markdown("---")
    st.markdown(
        f'<div class="section-title">⚙️ {script.framework} Project</div>',
        unsafe_allow_html=True,
    )

    # ── Project Overview ───────────────────────────────────────────────────
    ov_col1, ov_col2 = st.columns([1, 2])
    with ov_col1:
        st.markdown(
            f'<div class="glass-card glass-card-accent">'
            f'<div class="label">Framework</div>'
            f'<div class="value" style="font-family:Space Mono,monospace;">{script.framework}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if script.project_structure:
            st.markdown(
                f'<div class="glass-card">'
                f'<div class="label">Project Structure</div>'
                f'<div class="value">{_build_tree_html(script.project_structure)}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    with ov_col2:
        st.markdown(
            f'<div class="glass-card glass-card-green">'
            f'<div class="label" style="color:#34d399;">Execution Command</div>'
            f'<div class="value" style="font-family:Space Mono,monospace;font-size:0.9rem;color:#e2e8f0;">'
            f'{script.execution_command}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if script.design_notes:
            with st.expander("📐 Design Notes", expanded=False):
                st.markdown(script.design_notes)

    # ── Code Tabs ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📝 Source Files</div>',
        unsafe_allow_html=True,
    )

    tabs = ["🏗️ Page Object", "🧪 Tests"]
    tab_contents = [script.page_object_code, script.test_code]
    if script.conftest_code:
        tabs.append("🔧 conftest / Fixtures")
        tab_contents.append(script.conftest_code)
    if script.config_code:
        tabs.append("⚙️ Config")
        tab_contents.append(script.config_code)
    if script.requirements_txt:
        tabs.append("📦 Requirements")
        tab_contents.append(script.requirements_txt)

    code_tabs = st.tabs(tabs)
    for tab, content in zip(code_tabs, tab_contents):
        with tab:
            st.code(content, language=lang)

    # ── Setup Instructions ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">🚀 Setup & Run</div>',
        unsafe_allow_html=True,
    )

    setup_lines = "\n".join(f"$ {cmd}" for cmd in script.setup_instructions)
    st.code(setup_lines, language="bash")

    # ── Downloads ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Downloads</div>',
        unsafe_allow_html=True,
    )

    d_col1, d_col2, d_col3 = st.columns(3)
    with d_col1:
        try:
            zip_data = create_automation_zip(script)
            st.download_button(
                label="⬇️ Download Project ZIP",
                data=zip_data,
                file_name="automation_project.zip",
                mime="application/zip",
                key="auto_zip_dl",
            )
        except Exception as e:
            st.error(f"ZIP creation failed: {e}")

    with d_col2:
        if script.page_object_file_name and script.page_object_code:
            st.download_button(
                label=f"⬇️ {script.page_object_file_name}",
                data=script.page_object_code.encode("utf-8"),
                file_name=script.page_object_file_name,
                mime="text/plain",
                key="auto_po_dl",
            )

    with d_col3:
        st.download_button(
            label=f"⬇️ {script.test_file_name}",
            data=script.test_code.encode("utf-8"),
            file_name=script.test_file_name,
            mime="text/plain",
            key="auto_test_dl",
        )
