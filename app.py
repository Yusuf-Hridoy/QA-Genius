from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from constants import TAB_LABELS, GLOBAL_TOP_BAR, PAGE_META
from utils import load_model, validate_api_key, show_api_key_error, render_page_header

load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="QA-Genius: SQA Intelligence Suite",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════════════════════
# FORCE DARK MODE
# ══════════════════════════════════════════════════════════════════════════════
_FORCE_DARK_JS = """
<script>
(function() {
    const KEY = 'stTheme';
    const TARGET = 'Dark';
    const current = localStorage.getItem(KEY);
    if (current !== TARGET) {
        localStorage.setItem(KEY, TARGET);
        window.location.reload();
    }
})();
</script>
"""
st.markdown(_FORCE_DARK_JS, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════
def _load_css() -> str:
    css_path = Path(__file__).parent / "assets" / "style.css"
    with open(css_path, "r", encoding="utf-8") as f:
        return f"<style>{f.read()}</style>"

st.markdown(_load_css(), unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# GLOBAL TOP BAR
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(GLOBAL_TOP_BAR, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# FLOATING SCROLL-TO-TOP BUTTON
# ══════════════════════════════════════════════════════════════════════════════
_SCROLL_TOP = """
<script>
(function() {
    const btn = document.createElement('button');
    btn.innerHTML = '▲';
    btn.id = 'scroll-top-btn';
    btn.title = 'Back to top';
    btn.style.cssText = `
        position: fixed;
        bottom: 2rem;
        right: 2rem;
        z-index: 999999;
        width: 3rem;
        height: 3rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #7c3aed, #a78bfa);
        color: #fff;
        border: none;
        font-size: 1.2rem;
        cursor: pointer;
        box-shadow: 0 4px 20px rgba(124, 58, 237, 0.4);
        opacity: 0;
        visibility: hidden;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
    `;
    btn.onclick = function() {
        window.scrollTo({ top: 0, behavior: 'smooth' });
    };
    document.body.appendChild(btn);

    window.addEventListener('scroll', function() {
        if (window.scrollY > 300) {
            btn.style.opacity = '1';
            btn.style.visibility = 'visible';
        } else {
            btn.style.opacity = '0';
            btn.style.visibility = 'hidden';
        }
    });
})();
</script>
"""
st.markdown(_SCROLL_TOP, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# API KEY GUARD
# ══════════════════════════════════════════════════════════════════════════════
if not validate_api_key():
    show_api_key_error()

# ══════════════════════════════════════════════════════════════════════════════
# MODEL
# ══════════════════════════════════════════════════════════════════════════════
if "model" not in st.session_state:
    st.session_state["model"] = load_model()
model = st.session_state["model"]

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(TAB_LABELS)

# ══════════════════════════════════════════════════════════════════════════════
# TAB RENDERS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    meta = PAGE_META["story_analyzer"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_ambiguity import render as render_ambiguity
    render_ambiguity(model)

with tab2:
    meta = PAGE_META["test_cases"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_test_cases import render as render_test_cases
    render_test_cases(model)

with tab3:
    meta = PAGE_META["bug_report"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_bug_report import render as render_bug_report
    render_bug_report(model)

with tab4:
    meta = PAGE_META["quality"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_quality import render as render_quality
    render_quality(model)

with tab5:
    meta = PAGE_META["automation"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_automation import render as render_automation
    render_automation(model)

with tab6:
    meta = PAGE_META["schema"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_schema import render as render_schema
    render_schema(model)

with tab7:
    meta = PAGE_META["security"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_security import render as render_security
    render_security(model)

with tab8:
    meta = PAGE_META["performance"]
    render_page_header(meta["title"], meta["desc"], meta["icon"])
    from ui.tab_performance import render as render_performance
    render_performance(model)
