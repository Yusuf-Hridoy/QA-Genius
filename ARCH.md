# QA-Genius — Architecture Documentation

> This document explains how QA-Genius is built, what technologies power it, and how the pieces fit together.

---

## 1. Project Overview

**QA-Genius** is an AI-powered SQA (Software Quality Assurance) Intelligence Suite. It is a single-page Streamlit application with eight independent tabs, each covering a distinct phase of the QA lifecycle:

| # | Tab | Purpose |
|---|-----|---------|
| 1 | Story Analyzer | Detect ambiguity in user stories, score INVEST quality, generate Gherkin acceptance criteria |
| 2 | Test Cases | Generate structured test suites with BDD scenarios, traceability, and automation feasibility |
| 3 | Bug Report | Transform raw bug notes into production-grade bug reports |
| 4 | Quality Analytics | Compute quality health scores, trend analysis, and prioritized recommendations |
| 5 | Automation Script | Scaffold complete automation projects (Playwright, Selenium, Cypress) |
| 6 | Schema Validator | Validate API JSON payloads for structural, semantic, and security issues |
| 7 | Security Tests | Generate OWASP-mapped security test cases with real payloads |
| 8 | Performance Tests | Generate runnable k6 scripts with six load profiles and SLA assertions |

---

## 2. Tech Stack

| Layer | Technology | Version | Why It Was Chosen |
|-------|-----------|---------|-------------------|
| **UI Framework** | Streamlit | >=1.35 | Rapid Python-native UI prototyping; built-in widgets, session state, and theming |
| **LLM Orchestration** | LangChain Core | >=0.2.0 | Clean prompt -> model -> parser chaining with `|` operator |
| **LLM Provider** | LangChain Google GenAI | >=1.0.0 | Native integration with Google's Gemini models |
| **AI Model** | Google Gemini 2.5 Flash Lite | -- | Fast, cost-effective, strong structured-output compliance |
| **Structured Output** | Pydantic v2 | >=2.0.0 | Type-safe LLM response parsing; catches malformed outputs early |
| **Data Processing** | Pandas | >=2.0.0 | CSV export and tabular data manipulation |
| **Excel Export** | OpenPyXL | >=3.1.0 | Styled multi-sheet Excel workbooks for test cases and security reports |
| **Resilience** | Tenacity | >=8.0.0 | Exponential-backoff retry on transient API failures (429, timeout, ServerError) |
| **Config Management** | python-dotenv | >=1.0.0 | Load `GOOGLE_API_KEY` from `.env` without hardcoding secrets |
| **JSON Repair** | json-repair | -- | Fix common LLM JSON formatting errors (trailing commas, markdown fences) |

---

## 3. High-Level Architecture

```
User (Browser)
       |
       | HTTP (localhost:8501)
       v
Streamlit Runtime (app.py)
       |
       |-- Page config (wide layout, dark theme, collapsed sidebar)
       |-- CSS injection (assets/style.css)
       |-- API key guard (utils.validate_api_key)
       |-- Model loader (utils.load_model) -> cached in session
       |-- 8 tabs rendered from ui/tab_*.py
       v
Tab Module (e.g., ui/tab_test_cases.py)
       |
       |-- Streamlit form widgets (text_area, selectbox, multiselect, etc.)
       |-- Build full input string from form values
       |-- Call prompts.py::get_<tab>_prompt()
       |-- Chain: prompt | model | PydanticOutputParser
       |-- invoke_with_retry(chain, inputs)
       |-- Render result + export buttons
       v
prompts.py
       |
       |-- GLOBAL_RULES (applied to every prompt)
       |-- LIMITATIONS_INSTRUCTION
       |-- CONFIDENCE_INSTRUCTION
       |-- One prompt function per tab with domain expertise
       v
Google Gemini API (gemini-2.5-flash-lite, temp=0.3)
       |
       |-- Returns structured JSON matching Pydantic schema
```

### Key Design Principles

1. **Tab Isolation** -- Each tab is completely self-contained. No shared state, no conversation history.
2. **Structured Output First** -- Every LLM call returns JSON that is parsed into a Pydantic model.
3. **Prompt-as-Code** -- Prompts are version-controlled Python strings with explicit rules, examples, and constraints.
4. **Human-in-the-Loop** -- All outputs are starting points for human review, not final deliverables.

---

## 4. File Structure Deep Dive

| File / Folder | Purpose |
|--------------|---------|
| `app.py` | Entry point -- page config, dark mode JS, CSS injection, API key guard, model caching, tab rendering |
| `models.py` | Pydantic schemas for ALL LLM outputs -- TestCase, BugReport, QualityAnalysis, AutomationScript, SchemaValidationReport, AmbiguityAnalysis, SecurityReport, PerformanceTestSuite |
| `prompts.py` | LLM prompt engineering (the "brain") -- GLOBAL_RULES, _apply_global_rules(), one prompt function per tab with few-shot examples |
| `utils.py` | Shared utilities -- validate_api_key, load_model, invoke_with_retry, repair_llm_json, ZIP/Excel exporters, badge class mappers |
| `constants.py` | UI constants & styling maps -- TAB_LABELS, SEVERITY_BADGE_MAP, PAGE_META, GLOBAL_TOP_BAR |
| `requirements.txt` | Python dependencies |
| `.env` | GOOGLE_API_KEY (gitignored) |
| `assets/style.css` | Dark theme overrides, glass cards, badges |
| `ui/tab_ambiguity.py` | Story Analyzer UI & rendering |
| `ui/tab_test_cases.py` | Test Cases UI, filters, CSV/Excel export |
| `ui/tab_bug_report.py` | Bug Report UI, structured env fields |
| `ui/tab_quality.py` | Quality Analytics UI, scorecards, trends |
| `ui/tab_automation.py` | Automation Script UI, ZIP export |
| `ui/tab_schema.py` | Schema Validator UI, JSON formatting |
| `ui/tab_security.py` | Security Tests UI, payload library export |
| `ui/tab_performance.py` | Performance Tests UI, script & Grafana export |

---

## 5. How the Prompt System Works

### 5.1 Global Rules (Applied to Every Prompt)

`GLOBAL_RULES` in `prompts.py` is a constant string prepended to every system prompt via `_apply_global_rules()`. It enforces:

- **Value Classification**: Every output value must be labeled DERIVED, COMPUTED, or UNKNOWN
- **No Hallucination**: Unknown values must be marked [VERIFY], [NOT PROVIDED], or omitted
- **No Self-Incriminating Comments**: No "placeholder" or "TODO" comments in generated code
- **No Fabricated Values**: No invented prices, versions, percentages, or IDs
- **Pass/Fail Gate**: Before flagging any violation, verify constraint -> actual value -> satisfaction
- **Score Breakdowns**: Every numerical score must show components and weights
- **Double Reading**: Read input twice to ensure specificity
- **Tab Isolation**: Never reference content from other tabs

### 5.2 Prompt Function Pattern

Each tab has a dedicated prompt function:

```python
def get_<tab>_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", _apply_global_rules("""
            # Domain persona (e.g., "You are a Principal QA Engineer...")
            # Task description
            # Methodology (step-by-step)
            # Output rules with field definitions
            # Few-shot example
            {format_instructions}
        """)),
        ("human", "User input:\n{input_data}")
    ])
```

### 5.3 Prompt Engineering Techniques

| Technique | Where Used | Purpose |
|-----------|-----------|---------|
| **Persona Assignment** | Every prompt | Sets expertise level and output tone |
| **Few-Shot Examples** | Every prompt | Shows exact expected output format |
| **Step-by-Step Methodology** | Every prompt | Forces chain-of-thought reasoning |
| **Explicit Output Rules** | Every prompt | Constrains format, values, and structure |
| **Conditional Logic** | Security, Performance, Automation | Adapts output to user selections (stack, compliance, framework) |
| **Negative Constraints** | Automation, Performance | "Never use X", "Forbidden: Y" |
| **Scoring Rubrics** | Story Analyzer, Quality, Schema | Makes scoring transparent and reproducible |
| **Stack-Aware Generation** | Security, Test Cases, Automation | Generates technology-specific content based on user input |

---

## 6. How Structured Output Works

### 6.1 The Parsing Pipeline

```python
from langchain_core.output_parsers import PydanticOutputParser

parser = PydanticOutputParser(pydantic_object=TestCaseList)
chain = get_tc_prompt() | model | parser
result = invoke_with_retry(chain, {
    "user_story": user_input,
    "format_instructions": parser.get_format_instructions(),
})
# result is a TestCaseList Pydantic object
```

### 6.2 Why Pydantic?

- **Type Safety**: `result.test_cases` is a `List[TestCase]`, not a raw dict
- **Validation**: Validates types, required fields, and constraints at parse time
- **IDE Support**: Autocomplete and type checking in editors
- **Serialization**: Easy `.model_dump()` for JSON export
- **Error Handling**: Malformed LLM outputs raise parse errors that we can catch and retry

### 6.3 JSON Repair Fallback

For tabs where the model occasionally returns markdown-wrapped JSON (Security, Performance):

```python
raw_chain = sec_prompt | model
raw_text = invoke_with_retry(raw_chain, {...})
cleaned = repair_llm_json(raw_text)  # strips ```json fences, fixes trailing commas
result = sec_parser.parse(cleaned)
```

---

## 7. How the UI Works

### 7.1 Streamlit Configuration (`app.py`)

```python
st.set_page_config(
    page_title="QA-Genius: SQA Intelligence Suite",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)
```

- **Wide layout**: Maximizes content area for data-heavy outputs
- **Dark theme**: Forced via JavaScript injection into `localStorage`
- **Custom CSS**: Loaded from `assets/style.css` for glass cards, badges, and typography

### 7.2 Tab Rendering Pattern

Each `ui/tab_*.py` follows this pattern:

1. Show tip/instruction box
2. Render input form (text_area, selectbox, multiselect, etc.)
3. On button click:
   - Validate input
   - Build full input string
   - Call prompt -> model -> parser
   - Store result in `st.session_state`
4. If result exists in `session_state`:
   - Render executive summary/scorecards
   - Render detailed findings
   - Render export buttons (CSV, Excel, Markdown, JSON, ZIP)

### 7.3 Session State

Results are stored in `st.session_state` so they survive browser refreshes:

```python
st.session_state["tc_result"] = result   # Test Cases
st.session_state["bug_result"] = result  # Bug Report
# etc.
```

### 7.4 Export System

| Tab | Export Formats |
|-----|---------------|
| Story Analyzer | Markdown, JSON |
| Test Cases | CSV, Excel (.xlsx) |
| Bug Report | Markdown, JSON |
| Quality Analytics | Markdown, JSON |
| Automation Script | ZIP (full project), individual files |
| Schema Validator | Markdown, JSON |
| Security Tests | CSV, Excel (.xlsx), Payload Library (JSON) |
| Performance Tests | Script file, Execution Plan (.md), Grafana JSON, ZIP |

---

## 8. Resilience & Error Handling

### 8.1 Retry Logic (`utils.py`)

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def invoke_with_retry(chain, inputs: dict):
    return chain.invoke(inputs)
```

Retries on: `ConnectionError`, `TimeoutError`, Google GenAI `ServerError`, rate-limit `ClientError` (HTTP 429).

### 8.2 API Key Guard

If `GOOGLE_API_KEY` is missing, the app displays a friendly error with a link to get a key and calls `st.stop()`.

---

## 9. Configuration

### 9.1 Environment Variables

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_google_genai_api_key_here
```

### 9.2 Model Configuration

```python
# utils.py
@st.cache_resource
def load_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        temperature=0.3,  # Low creativity for deterministic QA outputs
    )
```

- **Temperature 0.3**: Balanced between consistency and slight variation. Low enough for reliable test cases and scripts, high enough to avoid robotic repetition.
- **Caching**: `@st.cache_resource` prevents reloading the model on every interaction.

---

## 10. How to Run

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate (Windows)
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure API key
echo GOOGLE_API_KEY=your_key_here > .env

# 5. Launch
streamlit run app.py
```

The app opens at `http://localhost:8501`.

---

## 11. Data Flow Example (Test Cases Tab)

```
User enters story + selects coverage focus + enters tech stack
                |
    ui/tab_test_cases.py builds full_input string
                |
    calls prompts.get_tc_prompt() -> ChatPromptTemplate
                |
    LangChain chain: prompt | model | parser
                |
    invoke_with_retry() -> Google Gemini API
                |
    Returns JSON -> PydanticOutputParser -> TestCaseList object
                |
    UI renders: summary dashboard, filterable test case cards, export buttons
                |
    User downloads CSV or Excel
```

---

## 12. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Single-page app, not multi-page** | All 8 workflows are visible at a glance; no navigation friction |
| **One prompt per tab, not a single generic prompt** | Domain-specific prompts produce higher-quality, more accurate outputs |
| **Pydantic over raw JSON** | Catches LLM errors early; enables type-safe UI rendering |
| **Temperature 0.3** | QA artifacts need consistency and accuracy, not creativity |
| **No database / no backend** | Stateless by design; every request is independent and reproducible |
| **Streamlit over React/Vue** | Python-native; rapid iteration; no separate frontend build step |
| **No conversation history** | Prevents context bleed; each tab is a clean slate |

---

## 13. Future Architecture (v2.0 Roadmap)

- **Provider Abstraction**: Swap Google Gemini for OpenAI GPT-4o or Anthropic Claude via a unified model interface
- **Regression Test Suite**: Pytest-based tests with mock LLM responses to verify prompt behavior
- **Docker Support**: Containerized deployment for consistent environments
- **Response Caching**: Cache identical inputs to reduce API costs
- **Hosted Demo**: Deploy to Streamlit Community Cloud

---

*Last updated: 2026-05-22 | Current version: v1.1*
