from pydantic import BaseModel
from typing import List, Optional


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
