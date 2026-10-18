import math
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, field_validator


class CategoryCount(BaseModel):
    category: str
    count: int


class PriorityCount(BaseModel):
    priority: str
    count: int


class TestSuiteSummary(BaseModel):
    total_generated: int
    category_breakdown: List[CategoryCount]
    priority_breakdown: List[PriorityCount]
    automation_coverage_potential: str
    coverage_gaps: List[str]
    recommendations: List[str]


class TestCase(BaseModel):
    id: str
    title: str
    category: str
    pre_conditions: str
    steps: List[str]
    expected_result: str
    priority: str
    test_data: Optional[str] = None
    bdd_scenario: Optional[str] = None
    automation_feasibility: str
    automation_effort: str
    tags: List[str]
    traceability: str


class TestCaseList(BaseModel):
    test_cases: List[TestCase]
    summary: TestSuiteSummary


class BugReport(BaseModel):
    title: str
    severity: str
    reproducibility_rate: str
    environment_details: str
    steps_to_reproduce: List[str]
    actual_result: str
    expected_result: str
    suggested_fix: Optional[str] = None
    root_cause_category: Optional[str] = None
    business_impact: Optional[str] = None
    affected_users: Optional[str] = None
    regression_risk: Optional[str] = None
    workaround: Optional[str] = None
    related_areas: Optional[List[str]] = None
    screenshot_annotations: Optional[List[str]] = None
    jira_labels: Optional[List[str]] = None
    suspected_pattern: Optional[str] = None
    related_issues: Optional[List[str]] = None
    investigation_steps: Optional[List[str]] = None


class QualityAnalysis(BaseModel):
    quality_health_score: int
    score_label: str
    passed: int
    failed: int
    blocked: int
    total: int
    pass_rate: str
    risk_areas: List[str]
    risk_summary: str
    recommendations: List[str]
    defect_density: Optional[str] = None
    mttr: Optional[str] = None
    sprint_health_score: Optional[int] = None
    trend_direction: Optional[str] = None
    blocker_analysis: Optional[str] = None
    flaky_tests: Optional[List[str]] = None
    ci_cd_health: Optional[str] = None
    action_owners: Optional[List[str]] = None
    quality_score_breakdown: Optional[str] = None
    sprint_score_breakdown: Optional[str] = None
    process_concerns: Optional[str] = None
    trend_table: Optional[str] = None


class AutomationScript(BaseModel):
    framework: str
    project_structure: List[str]
    page_object_file_name: Optional[str] = None
    page_object_code: Optional[str] = None
    test_file_name: str
    test_code: str
    conftest_file_name: Optional[str] = None
    conftest_code: Optional[str] = None
    config_file_name: Optional[str] = None
    config_code: Optional[str] = None
    requirements_txt: Optional[str] = None
    setup_instructions: List[str]
    execution_command: str
    design_notes: Optional[str] = None


class ValidationIssue(BaseModel):
    field: str
    path: Optional[str] = None
    issue_type: str
    severity: str
    description: str
    suggestion: str
    expected_type: Optional[str] = None
    actual_value: Optional[str] = None
    constraint_violated: Optional[str] = None


class SchemaValidationReport(BaseModel):
    overall_status: str
    compliance_score: int
    total_checks: int
    passed_checks: int
    failed_checks: int
    issues: List[ValidationIssue]
    schema_summary: str
    overall_recommendation: str
    missing_fields: Optional[List[str]] = None
    extra_fields: Optional[List[str]] = None
    security_concerns: Optional[List[str]] = None
    semantic_issues: Optional[List[str]] = None
    score_breakdown: Optional[str] = None


class VaguePhrase(BaseModel):
    phrase: str
    severity: str
    suggestion: str
    replacement: str


class AmbiguityAnalysis(BaseModel):
    ambiguity_score: int
    clarity_label: str
    invest_overall: str
    invest_independent: str
    invest_negotiable: str
    invest_valuable: str
    invest_estimable: str
    invest_small: str
    invest_testable: str
    vague_phrases: List[VaguePhrase]
    missing_elements: List[str]
    suggested_rewrites: List[str]
    generated_acceptance_criteria: List[str]
    risks: List[str]
    score_breakdown: Optional[str] = None
    recommended_split: Optional[List[str]] = None


# ══════════════════════════════════════════════════════════════════════════════
# SECURITY TEST CASE GENERATOR MODELS
# ══════════════════════════════════════════════════════════════════════════════

class OwaspCoverageItem(BaseModel):
    owasp_id: str
    category: str
    test_count: int
    status: str


class SecurityTestCase(BaseModel):
    id: str
    owasp_id: str
    owasp_category: str
    title: str
    description: str
    steps: List[str]
    sample_payloads: List[str]
    severity: str
    remediation: str
    tool_hint: str
    test_type: str


class SecuritySummary(BaseModel):
    total_tests: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    coverage_score: int
    overall_risk: str
    owasp_coverage: List[OwaspCoverageItem]
    key_findings: List[str]
    recommendations: List[str]


class SecurityReport(BaseModel):
    test_cases: List[SecurityTestCase]
    summary: SecuritySummary


# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE TEST SCENARIO GENERATOR MODELS
# ══════════════════════════════════════════════════════════════════════════════

class SlaAssertion(BaseModel):
    metric: str
    operator: str
    threshold: str
    severity: str


class LoadProfile(BaseModel):
    profile_type: str
    description: str
    duration: str
    ramp_up: str
    plateau: str
    ramp_down: str
    peak_vus: int
    target_tps: Optional[int] = None


class PerformanceScenario(BaseModel):
    id: str
    name: str
    description: str
    criticality: str
    user_flow_steps: List[str]
    api_endpoints: List[str]
    data_requirements: Optional[str] = None


class PerformanceTestSuite(BaseModel):
    framework: str
    critical_user_journeys: List[str]
    scenarios: List[PerformanceScenario]
    load_profiles: List[LoadProfile]
    sla_assertions: List[SlaAssertion]
    script_code: str
    script_file_name: str
    execution_plan: List[str]
    setup_instructions: List[str]
    run_command: str
    design_notes: Optional[str] = None
    grafana_dashboard: Optional[str] = None
    sample_csv: Optional[str] = None


class Rule(BaseModel):
    topic: str
    reading: str
    source_phrase: str


class NumberReading(BaseModel):
    name: str
    value: str
    source_phrase: str


class Interpretation(BaseModel):
    actors: List[str] = []
    rules: List[Rule] = []
    numbers: List[NumberReading] = []
    outcomes: List[str] = []
    assumptions: List[str] = []


def _severity_text(value: Any) -> str:
    """A fork severity from whatever the AI wrote. Unreadable text is medium."""
    text = str(value or "").strip().lower()
    if text in ("high", "medium", "low"):
        return text
    if text == "critical":
        return "high"
    if text == "moderate":
        return "medium"
    if text == "minor":
        return "low"
    return "medium"


class Fork(BaseModel):
    topic: str
    reading_a: str
    reading_b: str
    source_phrase: str
    severity: Literal["high", "medium", "low"]
    suggested_rewrite: str

    @field_validator("severity", mode="before")
    @classmethod
    def _tolerant_severity(cls, value: Any) -> str:
        return _severity_text(value)


class DuelFork(BaseModel):
    """One fork as Ship check needs it: the topic and how bad it is."""

    topic: str = ""
    severity: Literal["high", "medium", "low"] = "medium"

    @field_validator("severity", mode="before")
    @classmethod
    def _tolerant_severity(cls, value: Any) -> str:
        return _severity_text(value)


class DuelSummary(BaseModel):
    """What the browser keeps from an ambiguity duel, for Ship check."""

    agreement_pct: int = 0
    forks: List[DuelFork] = []


class DuelComparison(BaseModel):
    forks: List[Fork] = []
    agreements: List[str] = []


class GroupInsight(BaseModel):
    group_id: str
    kind: Literal["product bug", "test issue", "environment", "unknown"]
    likely_cause: str
    suggested_action: str

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in ("product bug", "test issue", "environment", "unknown"):
            return text
        if text in ("bug", "product", "product issue", "app bug"):
            return "product bug"
        if text in ("test", "flaky test", "test code", "test bug", "flaky"):
            return "test issue"
        if text in ("env", "infrastructure", "infra", "ci", "network"):
            return "environment"
        return "unknown"


class QualityInsightSummary(BaseModel):
    headline: str
    assessment: str
    groups: List[GroupInsight] = []
    flaky_advice: str = ""
    next_steps: List[str] = []


# ══════════════════════════════════════════════════════════════════════════════
# RISK RADAR (FMEA) MODELS
# ══════════════════════════════════════════════════════════════════════════════

RISK_CATEGORIES = (
    "security",
    "performance",
    "reliability",
    "data",
    "usability",
    "accessibility",
    "functional",
)

# What the AI tends to write instead of a category name.
_CATEGORY_SYNONYMS = {
    "perf": "performance",
    "load": "performance",
    "speed": "performance",
    "sec": "security",
    "auth": "security",
    "privacy": "security",
    "availability": "reliability",
    "resilience": "reliability",
    "stability": "reliability",
    "data integrity": "data",
    "integrity": "data",
    "ux": "usability",
    "a11y": "accessibility",
}
SCORE_FALLBACK = 3


def _one_score(value: Any) -> int:
    """A 1-5 score from whatever the AI wrote. Unreadable text scores 3."""
    if isinstance(value, bool):
        return SCORE_FALLBACK
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        # "4/5" and "4 out of 5" both mean 4.
        head = str(value or "").strip().split("/")[0].split()[:1]
        try:
            number = float(head[0]) if head else float("nan")
        except ValueError:
            return SCORE_FALLBACK
    if number != number:  # NaN
        return SCORE_FALLBACK
    rounded = int(math.floor(number + 0.5))
    return max(1, min(5, rounded))


class FailureMode(BaseModel):
    id: str = ""
    title: str
    category: str
    effect: str
    cause: str
    severity: int
    likelihood: int
    detectability: int
    severity_reason: str = ""
    likelihood_reason: str = ""
    detectability_reason: str = ""
    related_criteria: List[str] = []
    covered_by: List[str] = []
    test_idea: str = ""
    # "ai" or "principal-qa": who proposed this failure mode.
    source: str = "ai"

    @field_validator("severity", "likelihood", "detectability", mode="before")
    @classmethod
    def _tolerant_score(cls, value: Any) -> int:
        return _one_score(value)

    @field_validator("category", mode="before")
    @classmethod
    def _tolerant_category(cls, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in RISK_CATEGORIES:
            return text
        return _CATEGORY_SYNONYMS.get(text, "functional")


class RiskAnalysis(BaseModel):
    failure_modes: List[FailureMode] = []


# ══════════════════════════════════════════════════════════════════════════════
# SMART TEST MATRIX MODELS
# ══════════════════════════════════════════════════════════════════════════════

class ProposedFactor(BaseModel):
    name: str
    values: List[str] = []
    reason: str = ""          # one short sentence: why this matters for this story


class ProposedRule(BaseModel):
    if_factor: str
    if_value: str
    then_factor: str
    then_value: str
    reason: str = ""


class MatrixProposal(BaseModel):
    factors: List[ProposedFactor] = []
    rules: List[ProposedRule] = []
