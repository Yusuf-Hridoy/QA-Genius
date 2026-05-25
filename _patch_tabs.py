import re
import os

# Define patches per file
PATCHES = {
    "ui/tab_test_cases.py": {
        "schema": "TestCaseList",
        "prompt_func": "get_tc_prompt",
        "prompt_var": "user_story",
        "session_key": "tc_result",
        "tab_name": "Test Cases",
        "button_label": "⚡ Generate Test Cases",
        "button_key": "tc_btn",
        "spinner_text": "Analyzing requirements and architecting test suite...",
        "main_input": "user_story",
        "main_field": "User Story / Feature Requirement",
        "min_chars": 30,
        "max_chars": 5000,
    },
    "ui/tab_bug_report.py": {
        "schema": "BugReport",
        "prompt_func": "get_bug_prompt",
        "prompt_var": "raw_bug",
        "session_key": "bug_result",
        "tab_name": "Bug Report",
        "button_label": "🐛 Format Bug Report",
        "button_key": "bug_btn",
        "spinner_text": "Analyzing and formatting bug report...",
        "main_input": "raw_bug",
        "main_field": "Raw Bug Notes",
        "min_chars": 20,
        "max_chars": 3000,
    },
    "ui/tab_quality.py": {
        "schema": "QualityAnalysis",
        "prompt_func": "get_qa_prompt",
        "prompt_var": "exec_summary",
        "session_key": "qa_result",
        "tab_name": "Quality Analytics",
        "button_label": "📊 Analyse Quality",
        "button_key": "qa_btn",
        "spinner_text": "Computing quality intelligence...",
        "main_input": "exec_summary",
        "main_field": "Test Execution Summary",
        "min_chars": 10,
        "max_chars": 5000,
        "has_total_check": True,
    },
    "ui/tab_automation.py": {
        "schema": "AutomationScript",
        "prompt_func": "get_auto_prompt",
        "prompt_var": "scenario",
        "session_key": "auto_result",
        "tab_name": "Automation Script",
        "button_label": "⚙️ Generate Project",
        "button_key": "auto_btn",
        "spinner_text": "Architecting automation project...",
        "main_input": "scenario_desc",
        "main_field": "Test Scenario Description",
        "min_chars": 30,
        "max_chars": 5000,
    },
    "ui/tab_schema.py": {
        "schema": "SchemaValidationReport",
        "prompt_func": "get_sv_prompt",
        "prompt_var": "json_payload",
        "session_key": "sv_result",
        "tab_name": "Schema Validator",
        "button_label": "🔍 Validate Schema",
        "button_key": "sv_btn",
        "spinner_text": "Performing structural, semantic, and security analysis...",
        "main_input": "raw_json",
        "main_field": "API Response (JSON)",
        "min_chars": 2,
        "max_chars": 20000,
        "is_json": True,
    },
}


def add_imports(content: str, schema: str, tab_name: str) -> str:
    """Add parse_llm_response, show_error_actions, validators to imports."""
    # Find the utils import block and extend it
    old_utils = "from utils import (\n    invoke_with_retry,"
    new_utils = "from utils import (\n    invoke_with_retry,\n    parse_llm_response,\n    show_error_actions,"
    if old_utils in content:
        content = content.replace(old_utils, new_utils, 1)
    else:
        # Single-line import
        content = content.replace(
            "from utils import invoke_with_retry",
            "from utils import invoke_with_retry, parse_llm_response, show_error_actions",
            1
        )

    # Add validators import
    if "from validators import" not in content:
        # Find a good place to insert
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_idx = i + 1
        lines.insert(insert_idx, "from validators import validate_text_input, detect_suspicious_content, ValidationError")
        content = "\n".join(lines)

    return content


def patch_button_handler(content: str, cfg: dict) -> str:
    """Replace the button click handler with validation + raw chain + parse_llm_response."""
    schema = cfg["schema"]
    prompt_func = cfg["prompt_func"]
    prompt_var = cfg["prompt_var"]
    session_key = cfg["session_key"]
    tab_name = cfg["tab_name"]
    button_label = cfg["button_label"]
    button_key = cfg["button_key"]
    spinner_text = cfg["spinner_text"]
    main_input = cfg["main_input"]
    main_field = cfg["main_field"]
    min_chars = cfg["min_chars"]
    max_chars = cfg["max_chars"]
    is_json = cfg.get("is_json", False)
    has_total_check = cfg.get("has_total_check", False)

    # Find the pattern: parser = PydanticOutputParser...
    parser_pattern = rf"({main_input}_parser|(\w+)_parser) = PydanticOutputParser\(pydantic_object={schema}\)"
    parser_match = re.search(parser_pattern, content)
    parser_name = parser_match.group(1) if parser_match else f"{main_input}_parser"

    # Build validation block
    if is_json:
        validate_block = f"""        try:
            validated_input = validate_json_input(
                {main_input}, "{main_field}", max_chars={max_chars}
            )
        except ValidationError as e:
            st.error(str(e))
            return"""
    elif has_total_check:
        validate_block = f"""        total = tests_passed + tests_failed + tests_blocked + tests_skipped
        if total == 0:
            st.warning("Please enter test execution counts.")
            return"""
    else:
        validate_block = f"""        try:
            validated_input = validate_text_input(
                {main_input}, "{main_field}", min_chars={min_chars}, max_chars={max_chars}
            )
            is_suspicious, msg = detect_suspicious_content(validated_input)
            if is_suspicious:
                st.warning(msg + " Please rephrase as a normal QA request.")
                return
        except ValidationError as e:
            st.error(str(e))
            return"""

    # Build the full replacement for the button block
    # We need to find the exact block from "if st.button(...)" to the end of the try/except

    # Pattern to match the old button handler
    old_pattern = rf"(    if st\.button\(\"{re.escape(button_label)}\", key=\"{button_key}\"\):\n)(.*?)(        with st\.spinner\(\"{re.escape(spinner_text)}\"\):\n)(.*?)(                try:\n                    (\w+) = invoke_with_retry\(chain, \{{\n                        \"{prompt_var}\": (.*?),\n                        \"format_instructions\": (.*?)\.get_format_instructions\(\),\n                    \}}\)\n                    st\.session_state\[\"{session_key}\"\] = (\w+)\n                except Exception as e:\n                    st\.error\(f\"Generation error: {{e}}\"\)\n                    return)"

    match = re.search(old_pattern, content, re.DOTALL)
    if not match:
        print(f"  WARNING: Could not find button handler pattern for {tab_name}")
        return content

    # Extract the parts we need to preserve
    pre_spinner = match.group(2)  # The validation/warning logic before spinner

    # Build new handler
    if has_total_check:
        new_block = f"""    if st.button("{button_label}", key="{button_key}"):
{validate_block}

        with st.spinner("{spinner_text}"):
            {prompt_func} = {prompt_func}()
            raw_chain = {prompt_func} | model
            try:
                raw = invoke_with_retry(raw_chain, {{
                    "{prompt_var}": exec_summary,
                    "format_instructions": {parser_name}.get_format_instructions(),
                }})
                if hasattr(raw, "content"):
                    raw = raw.content
                result = parse_llm_response(raw, {schema}, tab_name="{tab_name}")
                if result is None:
                    show_error_actions("{tab_name}")
                    return
                st.session_state["{session_key}"] = result
            except Exception as e:
                st.error(f"Generation error: {{e}}")
                show_error_actions("{tab_name}", str(e))
                return"""
    elif is_json:
        new_block = f"""    if st.button("{button_label}", key="{button_key}"):
{validate_block}

        with st.spinner("{spinner_text}"):
            {prompt_func} = {prompt_func}()
            raw_chain = {prompt_func} | model
            try:
                raw = invoke_with_retry(raw_chain, {{
                    "{prompt_var}": json.dumps(validated_input, indent=2),
                    "format_instructions": {parser_name}.get_format_instructions(),
                }})
                if hasattr(raw, "content"):
                    raw = raw.content
                result = parse_llm_response(raw, {schema}, tab_name="{tab_name}")
                if result is None:
                    show_error_actions("{tab_name}")
                    return
                st.session_state["{session_key}"] = result
            except Exception as e:
                st.error(f"Generation error: {{e}}")
                show_error_actions("{tab_name}", str(e))
                return"""
    else:
        new_block = f"""    if st.button("{button_label}", key="{button_key}"):
{validate_block}

        with st.spinner("{spinner_text}"):
            {prompt_func} = {prompt_func}()
            raw_chain = {prompt_func} | model
            try:
                raw = invoke_with_retry(raw_chain, {{
                    "{prompt_var}": full_input,
                    "format_instructions": {parser_name}.get_format_instructions(),
                }})
                if hasattr(raw, "content"):
                    raw = raw.content
                result = parse_llm_response(raw, {schema}, tab_name="{tab_name}")
                if result is None:
                    show_error_actions("{tab_name}")
                    return
                st.session_state["{session_key}"] = result
            except Exception as e:
                st.error(f"Generation error: {{e}}")
                show_error_actions("{tab_name}", str(e))
                return"""

    content = content[:match.start()] + new_block + content[match.end():]
    return content


def patch_display_fallback(content: str, session_key: str, tab_name: str, schema: str) -> str:
    """Wrap display section in try/except with fallback."""
    # Find the display results section
    display_start = f'    if "{session_key}" not in st.session_state:\n        return\n'
    if display_start not in content:
        display_start = f'    if "{session_key}" not in st.session_state:\n        return\n\n'

    if display_start not in content:
        print(f"  WARNING: Could not find display section for {tab_name}")
        return content

    idx = content.index(display_start) + len(display_start)

    # Find the end of the function (last line with indentation)
    # We'll insert the try/except around the remaining content
    remaining = content[idx:]

    # We need to dedent the remaining content by 4 spaces and wrap it
    lines = remaining.split("\n")
    # Don't wrap empty trailing lines
    while lines and lines[-1].strip() == "":
        lines.pop()

    # Build wrapped content
    fallback = f"""    result = st.session_state["{session_key}"]

    try:
        _render_{session_key}(result)
    except Exception as e:
        st.error(
            "The AI response was generated successfully, but couldn't be displayed in the standard view. "
            "Showing the raw response below."
        )
        with st.expander("Raw Response (for debugging)", expanded=False):
            try:
                st.json(result.model_dump())
            except Exception:
                st.code(str(result))
        show_error_actions("{tab_name}", str(e))


def _render_{session_key}(result):
    \"\"\"Render {tab_name} results.\"\"\"\n"""

    # Add the remaining lines, keeping their indentation
    wrapped_lines = []
    for line in lines:
        if line.startswith("    "):
            wrapped_lines.append("    " + line[4:])  # Keep relative indent but add one more level
        elif line.strip() == "":
            wrapped_lines.append("")
        else:
            wrapped_lines.append("    " + line)

    new_content = content[:idx] + fallback + "\n".join(wrapped_lines)
    return new_content


def patch_file(filepath: str, cfg: dict):
    print(f"Patching {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Step 1: Add imports
    content = add_imports(content, cfg["schema"], cfg["tab_name"])

    # Step 2: Patch button handler
    content = patch_button_handler(content, cfg)

    # Step 3: Patch display fallback
    content = patch_display_fallback(content, cfg["session_key"], cfg["tab_name"], cfg["schema"])

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  ✓ Updated")
    else:
        print(f"  = No changes")


# Run patches
for filepath, cfg in PATCHES.items():
    patch_file(filepath, cfg)

print("Done patching chain-based tabs.")
