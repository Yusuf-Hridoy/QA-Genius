import json

import streamlit as st
from langchain_core.output_parsers import PydanticOutputParser

from models import AmbiguityAnalysis
from prompts import get_ambiguity_prompt
from utils import (
    invoke_with_retry,
    get_ambiguity_score_class,
    get_invest_badge_class,
    parse_llm_response,
    show_error_actions,
)
from validators import validate_text_input, detect_suspicious_content, ValidationError


def render(model):
    st.markdown(
        '<div class="tip-box">💡 Paste a user story or requirement. The AI analyzes it for '
        "ambiguity, vague language, missing acceptance criteria, and INVEST quality — then generates "
        "a clearer rewrite with Gherkin acceptance criteria.</div>",
        unsafe_allow_html=True,
    )

    project_context = st.text_area(
        "Project Context (optional)",
        placeholder="e.g. fintech mobile app, B2B healthcare SaaS, internal tooling",
        height=60,
        key="amb_context",
    )

    story_type = st.selectbox(
        "Story Type",
        ["User Story", "Technical Story", "Bug Fix Story", "Spike/Research"],
        key="amb_type",
    )

    user_story = st.text_area(
        "User Story / Requirement",
        placeholder='e.g. "As a user, I want a fast login process so that I can access my account quickly."',
        height=120,
        key="amb_input",
    )

    amb_parser = PydanticOutputParser(pydantic_object=AmbiguityAnalysis)

    if st.button("📝 Analyze Story", key="amb_btn"):
        try:
            validated_story = validate_text_input(
                user_story, "User Story / Requirement", min_chars=20, max_chars=3000
            )
            validated_context = validate_text_input(
                project_context, "Project Context", min_chars=0, max_chars=1000, required=False
            )
            is_suspicious, msg = detect_suspicious_content(validated_story)
            if is_suspicious:
                st.warning(msg + " Please rephrase as a normal QA request.")
                return
        except ValidationError as e:
            st.error(str(e))
            return

        with st.spinner("Analyzing story quality and ambiguity..."):
            amb_prompt = get_ambiguity_prompt()
            raw_chain = amb_prompt | model
            full_input = (
                f"Story Type: {story_type}\n"
                f"Project Context: {validated_context or 'Not provided'}\n\n"
                f"User Story / Requirement:\n{validated_story}"
            )
            try:
                raw = invoke_with_retry(raw_chain, {
                    "user_story": full_input,
                    "format_instructions": amb_parser.get_format_instructions(),
                })
                if hasattr(raw, "content"):
                    raw = raw.content
                result = parse_llm_response(raw, AmbiguityAnalysis, tab_name="Story Analyzer")
                if result is None:
                    show_error_actions("Story Analyzer")
                    return
                st.session_state["amb_result"] = result
            except Exception as e:
                st.error(f"Generation error: {e}")
                show_error_actions("Story Analyzer", str(e))
                return

    # ─────────────────────────────────────────────────────────────────────────
    # DISPLAY RESULTS
    # ─────────────────────────────────────────────────────────────────────────
    if "amb_result" not in st.session_state:
        return

    result = st.session_state["amb_result"]

    try:
        _render_ambiguity_results(result)
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
        show_error_actions("Story Analyzer", str(e))


def _render_ambiguity_results(result):
    """Render ambiguity analysis results."""

    score_class = get_ambiguity_score_class(result.ambiguity_score)

    st.markdown("---")
    st.markdown(
        '<div class="section-title">📝 Ambiguity Analysis Report</div>',
        unsafe_allow_html=True,
    )

    # ── Executive Scorecard ────────────────────────────────────────────────
    st.markdown(
        f'<div class="glass-card" style="text-align:center;padding:2rem 1rem;">'
        f'<div class="label" style="text-align:center;">Ambiguity Score</div>'
        f'<div class="score-num {score_class}">{result.ambiguity_score}</div>'
        f'<div class="score-label {score_class}">{result.clarity_label}</div>'
        f'<div style="font-family:Space Mono,monospace;font-size:0.75rem;color:#475569;margin-top:0.8rem;">'
        f'Lower is better — 0 = Crystal Clear, 100 = Unusable</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    if result.score_breakdown:
        st.markdown(
            f'<div class="glass-card" style="margin-top:0.8rem;">'
            f'<div class="label" style="color:#60a5fa;">Score Breakdown</div>'
            f'<div style="color:#e2e8f0;font-size:0.85rem;white-space:pre-wrap;margin-top:0.3rem;">{result.score_breakdown}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    if result.recommended_split:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">✂️ Recommended Split</div>',
            unsafe_allow_html=True,
        )
        for i, split in enumerate(result.recommended_split, 1):
            st.markdown(
                f'<div style="padding:0.4rem 0;padding-left:1rem;">'
                f'<span style="color:#a78bfa;font-family:Space Mono,monospace;margin-right:0.5rem;">{i}.</span>'
                f'<span style="color:#e2e8f0;font-size:0.9rem;">{split}</span></div>',
                unsafe_allow_html=True,
            )

    # ── INVEST Breakdown ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📐 INVEST Quality Breakdown</div>',
        unsafe_allow_html=True,
    )

    invest_items = [
        ("Independent", result.invest_independent),
        ("Negotiable", result.invest_negotiable),
        ("Valuable", result.invest_valuable),
        ("Estimable", result.invest_estimable),
        ("Small", result.invest_small),
        ("Testable", result.invest_testable),
    ]

    st.markdown(
        '<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:0.8rem;">',
        unsafe_allow_html=True,
    )
    for name, status in invest_items:
        badge_cls = get_invest_badge_class(status)
        # Handle both old em-dash and new double-dash separators
        short = status
        for sep in ["--", "—"]:
            if sep in short:
                short = short.split(sep)[0].strip()
                break
        st.markdown(
            f'<div class="stat-tile">'
            f'<span class="badge {badge_cls}" style="font-size:0.75rem;">{short}</span>'
            f'<div class="lbl" style="margin-top:0.5rem;">{name}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f'<div style="text-align:center;margin-top:0.8rem;font-family:Space Mono,monospace;'
        f'font-size:0.75rem;color:#475569;">{result.invest_overall}</div>',
        unsafe_allow_html=True,
    )

    # ── Risks ──────────────────────────────────────────────────────────────
    if result.risks:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">⚠️ Risks if Developed As-Is</div>',
            unsafe_allow_html=True,
        )
        for risk in result.risks:
            st.markdown(
                f'<div style="padding:0.5rem 0;padding-left:1rem;">'
                f'<span style="color:#f87171;margin-right:0.5rem;">▸</span>'
                f'<span style="color:#e2e8f0;font-size:0.9rem;">{risk}</span></div>',
                unsafe_allow_html=True,
            )

    # ── Vague Phrases ──────────────────────────────────────────────────────
    if result.vague_phrases:
        st.markdown("---")
        st.markdown(
            f'<div class="section-title">🔍 {len(result.vague_phrases)} Vague Phrase(s) Found</div>',
            unsafe_allow_html=True,
        )

        for vp in result.vague_phrases:
            sev = vp.severity.lower()
            badge_cls = f"badge-{sev}" if sev in ["critical", "high", "medium", "low"] else "badge-medium"
            with st.expander(f"**{vp.phrase}** — {vp.severity}", expanded=False):
                st.markdown(
                    f'<div style="display:flex;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.8rem;">'
                    f'<span class="badge {badge_cls}">{vp.severity}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Problem:** {vp.suggestion}")
                st.markdown(
                    f'<div style="background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.15);'
                    f'border-radius:8px;padding:0.8rem;margin-top:0.5rem;">'
                    f'<div style="font-size:0.65rem;color:#34d399;text-transform:uppercase;letter-spacing:0.1em;">'
                    f'Suggested Replacement</div>'
                    f'<div style="font-family:Space Mono,monospace;font-size:0.85rem;color:#e2e8f0;margin-top:0.3rem;">'
                    f'{vp.replacement}</div></div>',
                    unsafe_allow_html=True,
                )

    # ── Missing Elements ───────────────────────────────────────────────────
    if result.missing_elements:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">❓ Missing Elements</div>',
            unsafe_allow_html=True,
        )
        for me in result.missing_elements:
            st.markdown(
                f'<div style="padding:0.4rem 0;padding-left:1rem;">'
                f'<span style="color:#fbbf24;margin-right:0.5rem;">◆</span>'
                f'<span style="color:#e2e8f0;font-size:0.9rem;">{me}</span></div>',
                unsafe_allow_html=True,
            )

    # ── Suggested Rewrites ─────────────────────────────────────────────────
    if result.suggested_rewrites:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">✏️ Suggested Rewrites</div>',
            unsafe_allow_html=True,
        )
        for i, rw in enumerate(result.suggested_rewrites, 1):
            st.markdown(
                f'<div style="padding:0.4rem 0;padding-left:1rem;">'
                f'<span style="color:#60a5fa;font-family:Space Mono,monospace;margin-right:0.5rem;">{i}.</span>'
                f'<span style="color:#e2e8f0;font-size:0.9rem;">{rw}</span></div>',
                unsafe_allow_html=True,
            )

    # ── Generated Acceptance Criteria ──────────────────────────────────────
    if result.generated_acceptance_criteria:
        st.markdown("---")
        st.markdown(
            '<div class="section-title">✅ Generated Acceptance Criteria (Gherkin)</div>',
            unsafe_allow_html=True,
        )
        for ac in result.generated_acceptance_criteria:
            st.code(ac, language="gherkin")

    # ── Exports ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        '<div class="section-title">📥 Exports</div>',
        unsafe_allow_html=True,
    )

    d1, d2 = st.columns(2)
    with d1:
        md_content = f"""# Ambiguity Analysis Report

## Score
| Metric | Value |
|--------|-------|
| **Ambiguity Score** | {result.ambiguity_score}/100 |
| **Clarity Label** | {result.clarity_label} |

## INVEST Quality
| Dimension | Status |
|-----------|--------|
| Independent | {result.invest_independent} |
| Negotiable | {result.invest_negotiable} |
| Valuable | {result.invest_valuable} |
| Estimable | {result.invest_estimable} |
| Small | {result.invest_small} |
| Testable | {result.invest_testable} |
| **Overall** | {result.invest_overall} |

## Risks
{chr(10).join([f'- {r}' for r in result.risks])}

## Vague Phrases
{chr(10).join([f"### {vp.phrase} ({vp.severity})\n- **Problem:** {vp.suggestion}\n- **Replacement:** {vp.replacement}" for vp in result.vague_phrases])}

## Missing Elements
{chr(10).join([f'- {m}' for m in result.missing_elements])}

## Suggested Rewrites
{chr(10).join([f'{i+1}. {r}' for i, r in enumerate(result.suggested_rewrites)])}

## Acceptance Criteria
{chr(10).join([f'```gherkin\n{ac}\n```' for ac in result.generated_acceptance_criteria])}
"""
        st.download_button(
            label="⬇️ Download Markdown Report",
            data=md_content.encode("utf-8"),
            file_name="ambiguity_analysis.md",
            mime="text/markdown",
            key="amb_md_dl",
        )

    with d2:
        json_content = json.dumps(result.model_dump(), indent=2)
        st.download_button(
            label="⬇️ Download JSON",
            data=json_content.encode("utf-8"),
            file_name="ambiguity_analysis.json",
            mime="application/json",
            key="amb_json_dl",
        )
