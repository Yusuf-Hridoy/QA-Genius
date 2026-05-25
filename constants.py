TAB_LABELS = [
    "📝  Story Analyzer",
    "🧪  Test Cases",
    "🐛  Bug Report",
    "📊  Quality Analytics",
    "⚙️  Automation Script",
    "🔍  Schema Validator",
    "🔒  Security Tests",
    "⚡  Performance Tests",
]

SEVERITY_BADGE_MAP = {
    "high": "badge-high",
    "medium": "badge-medium",
    "low": "badge-low",
    "critical": "badge-critical",
}

SEVERITY_ORDER = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
}

# ── Test Case Priority ───────────────────────────────────────────────────────
PRIORITY_BADGE_MAP = {
    "high": "badge-critical",
    "medium": "badge-medium",
    "low": "badge-low",
}

PRIORITY_ORDER = {
    "High": 0,
    "Medium": 1,
    "Low": 2,
}

# ── Test Case Category ───────────────────────────────────────────────────────
CATEGORY_BADGE_MAP = {
    "functional": "badge-functional",
    "edge case": "badge-edge",
    "negative": "badge-negative",
    "boundary": "badge-boundary",
}

CATEGORY_ORDER = {
    "Functional": 0,
    "Boundary": 1,
    "Edge Case": 2,
    "Negative": 3,
}

# ── Automation Feasibility ───────────────────────────────────────────────────
AUTO_FEASIBILITY_MAP = {
    "high": "badge-good",
    "medium": "badge-medium",
    "low": "badge-risk",
}

AUTO_EFFORT_MAP = {
    "low": "badge-good",
    "moderate": "badge-medium",
    "high": "badge-risk",
    "quick": "badge-good",
    "complex": "badge-risk",
}

# ── Bug Report Root Cause ────────────────────────────────────────────────────
ROOT_CAUSE_BADGE_MAP = {
    "frontend": "badge-functional",
    "backend": "badge-regression",
    "api": "badge-smoke",
    "database": "badge-edge",
    "config": "badge-negative",
    "race condition": "badge-critical",
    "ui/ux": "badge-medium",
    "performance": "badge-boundary",
    "security": "badge-critical",
    "integration": "badge-high",
    "environment": "badge-low",
}

# ── Regression Risk ──────────────────────────────────────────────────────────
REGRESSION_RISK_MAP = {
    "high": "badge-critical",
    "medium": "badge-medium",
    "low": "badge-good",
}

# ── Trend Direction ──────────────────────────────────────────────────────────
TREND_BADGE_MAP = {
    "improving": "badge-good",
    "stable": "badge-medium",
    "degrading": "badge-risk",
}

# ── Issue Type ───────────────────────────────────────────────────────────────
ISSUE_TYPE_BADGE_MAP = {
    "missing_field": "badge-critical",
    "null_value": "badge-critical",
    "wrong_type": "badge-high",
    "unexpected_key": "badge-medium",
    "format_error": "badge-medium",
    "semantic_violation": "badge-high",
    "security_risk": "badge-critical",
}

# ── INVEST Score ─────────────────────────────────────────────────────────────
INVEST_BADGE_MAP = {
    "pass": "badge-good",
    "partial": "badge-medium",
    "fail": "badge-risk",
}

# ── Security Test Type ───────────────────────────────────────────────────────
TEST_TYPE_BADGE_MAP = {
    "exploitation": "badge-critical",
    "defensive": "badge-good",
    "reconnaissance": "badge-smoke",
}

# ── OWASP Severity ───────────────────────────────────────────────────────────
OWASP_SEVERITY_ORDER = {
    "Critical": 0,
    "High": 1,
    "Medium": 2,
    "Low": 3,
}

# ── OWASP Coverage Status ────────────────────────────────────────────────────
OWASP_STATUS_BADGE_MAP = {
    "covered": "badge-good",
    "partial": "badge-medium",
    "missing": "badge-risk",
}

# ── Security Risk Level ──────────────────────────────────────────────────────
RISK_LEVEL_BADGE_MAP = {
    "critical": "badge-critical",
    "high": "badge-high",
    "medium": "badge-medium",
    "low": "badge-good",
}

# ── Performance Framework ────────────────────────────────────────────────────
PERF_FRAMEWORK_BADGE_MAP = {
    "k6": "badge-good",
    "jmeter": "badge-high",
    "artillery": "badge-smoke",
}

# ── Load Profile ─────────────────────────────────────────────────────────────
LOAD_PROFILE_BADGE_MAP = {
    "smoke": "badge-good",
    "average load": "badge-medium",
    "spike": "badge-critical",
    "soak": "badge-boundary",
    "stress": "badge-high",
    "breakpoint": "badge-risk",
}

# ── Criticality ──────────────────────────────────────────────────────────────
CRITICALITY_BADGE_MAP = {
    "critical": "badge-critical",
    "high": "badge-high",
    "medium": "badge-medium",
}

HEADER = """
<div class="qa-header">
    <h1>🧠 QA<span>-Genius</span></h1>
    <p>// The SQA Intelligence Suite — powered by AI</p>
</div>
"""

# ═════════════════════════════════════════════════════════════════════════════
# PAGE METADATA for sidebar navigation & headers
# ═════════════════════════════════════════════════════════════════════════════
PAGE_META = {
    "story_analyzer": {
        "title": "Story Analyzer",
        "desc": "AI-powered story quality analysis",
        "icon": "📝",
    },
    "test_cases": {
        "title": "Test Cases",
        "desc": "AI-powered analysis",
        "icon": "🧪",
    },
    "bug_report": {
        "title": "Bug Report",
        "desc": "Production-grade bug report formatter",
        "icon": "🐛",
    },
    "quality": {
        "title": "Quality Analytics",
        "desc": "Quality health & sprint intelligence",
        "icon": "📊",
    },
    "automation": {
        "title": "Automation Script",
        "desc": "Generate runnable automation projects",
        "icon": "⚙️",
    },
    "schema": {
        "title": "Schema Validator",
        "desc": "Structural, semantic & security validation",
        "icon": "🔍",
    },
    "security": {
        "title": "Security Tests",
        "desc": "OWASP-mapped security test generation",
        "icon": "🔒",
    },
    "performance": {
        "title": "Performance Tests",
        "desc": "Load profiles, SLA assertions & scripts",
        "icon": "⚡",
    },
}

# ═════════════════════════════════════════════════════════════════════════════
# SHARED UI COMPONENTS
# ═════════════════════════════════════════════════════════════════════════════
SIDEBAR_BRANDING = """
<div class="sidebar-brand">
    <div class="sb-logo-row">
        <div class="sb-logo">🧠</div>
        <div class="sb-title">QA-Genius</div>
    </div>
    <div class="sb-version">v2.0 • AI</div>
</div>
"""

GLOBAL_TOP_BAR = """
<div class="global-top-bar">
    <div class="gtb-left">
        <div class="gtb-logo">🧠</div>
        <div>
            <div class="gtb-title">QA-Genius</div>
            <div class="gtb-subtitle">// The SQA Intelligence Suite</div>
        </div>
    </div>
</div>
"""

SIDEBAR_FOOTER = """
<div class="sidebar-footer">
    <span>✨</span> Powered by AI
</div>
"""
