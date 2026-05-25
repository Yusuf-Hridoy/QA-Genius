# 🧠 QA-Genius — SQA Intelligence Suite

A Streamlit-based AI workspace for QA engineers — seven structured workflows covering the QA lifecycle from user story refinement to performance testing. Outputs are AI-generated starting points designed for human review and iteration.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B)
![GenAI](https://img.shields.io/badge/AI-Google%20GenAI-4285F4)


---

## 🎯 Why I Built This

<!-- TODO: Replace this paragraph with your own voice. Two or three sentences. -->
<!-- Possible angles: -->
<!-- - Personal: 2+ years in QA automation, wanted to test how far prompt engineering can take AI-assisted QA workflows -->
<!-- - Technical: curious where structured prompt engineering for technical domains breaks down -->
<!-- - Practical: covers the QA lifecycle as I see it day-to-day, from sprint planning to perf testing -->

I built QA-Genius to explore how far prompt engineering can take AI-assisted QA workflows — and where it breaks down.
The seven tabs reflect the QA lifecycle as I see it from two years of automation work: from refining vague user stories at sprint planning,
---

## ✨ What It Does

QA-Genius generates structured QA artifacts from plain-text inputs — user stories, API responses, app descriptions, sprint summaries. Each tab is independent, with its own prompt, structured Pydantic output schema, and export options.

| Module | What It Generates |
|--------|-------------------|
| 📝 **Story Analyzer** | Ambiguity report with INVEST evaluation, vague-phrase detection, suggested rewrites, and Gherkin acceptance criteria. |
| 🧪 **Test Cases** | Functional, negative, boundary, and edge-case test cases with steps, test data, BDD scenarios, traceability tags, and a coverage-gap summary. |
| 🐛 **Bug Report** | Structured bug reports from raw notes — title, environment, repro steps, severity/priority, suspected pattern, and investigation checklist. |
| 📊 **Quality Analytics** | Sprint quality report — pass rate, defect density, MTTR analysis, trend comparison, prioritized recommendations with owners. |
| ⚙️ **Automation Script** | Playwright project scaffolding — test files, config, package.json, and run instructions. JS or TS, flat or POM. |
| 🔍 **Schema Validator** | Validates real API responses against structural, semantic, and security expectations — catches PII exposure, type mismatches, format violations. |
| 🔒 **Security Tests** | OWASP Top 10–mapped test cases with payloads, severity, remediation, and tool hints. Adapts to stated stack and compliance context. |
| ⚡ **Performance Tests** | k6 scripts with six load profiles (Smoke → Breakpoint), per-endpoint SLA thresholds, correlation patterns, and execution plan. |

---

## 📸 Screenshots
<img src="https://res.cloudinary.com/dncod5rnj/image/upload/v1778323869/qageni_h7bzkz.png" width="800"/>



---

## ⚠️ Current Limitations

This is v1.0. Outputs are AI-generated and require human review before use in production contexts. Known gaps under active improvement:

- **Hallucination on specific values** — Generated scripts and reports may contain plausible-but-fabricated values (specific prices, version numbers, IDs, scoring percentages). Verify all specifics before using outputs as deliverables.
- **Generic outputs in some scenarios** — Some tabs default to generic best-practice content rather than fully grounding in user input. Quality Analytics, Schema Validator, and Performance Tests are most affected.
- **No automated tests yet** — Tool behavior is verified manually via a documented input set. Regression tests are on the roadmap.
- **Single-LLM dependency** — Currently coupled to Google Gemini. Provider abstraction is planned for v2.
- **No deployment target** — Runs locally only; hosted demo not yet available.

The detailed improvement backlog covering all seven tabs is documented in [`IMPROVEMENTS.md`](IMPROVEMENTS.md). v1.1 addresses the highest-impact items (correlation in Performance Tests, false-positive reduction in Schema Validator, environment-field handling in Bug Report, and trend analysis in Quality Analytics).

---

## 🏗️ How It Works

The architecture is deliberately simple — one Streamlit page per tab, one prompt function per tab, structured output via Pydantic.

```
User input (Streamlit form)
    ↓
prompts.py::build_<tab>_prompt(input_data)
    ↓
LangChain → 
    ↓
Pydantic schema parsing (models.py)
    ↓
UI rendering (ui/tab_*.py) + export options
```

Tabs do not share state. Each form submission is a fresh API call with no conversation history, which keeps prompts isolated and outputs deterministic across sessions.

---

## 🚀 Quick Start

```bash
streamlit run app.py
```

The app launches at `http://localhost:8501` with a dark-themed wide layout.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **UI** | Streamlit (custom CSS, dark theme, wide layout) |
| **LLM Orchestration** | LangChain |
| **Model** | Google Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`) |
| **Structured Output** | Pydantic v2 |
| **Data Processing** | Pandas, OpenPyXL (Excel export) |
| **Resilience** | Tenacity (exponential backoff retry) |
| **Configuration** | python-dotenv |

---

## 📦 Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/qa-genius.git
cd qa-genius
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure your API key

Create a `.env` file in the project root:

```env
GOOGLE_API_KEY=your_google_genai_api_key_here
```

Use any api key which you have 

### 5. Run the app

```bash
streamlit run app.py
```

---

## 📁 Project Structure

```
qa-genius/
├── app.py                      # Streamlit entry point — layout, tabs, theming
├── models.py                   # Pydantic schemas for all LLM outputs
├── constants.py                # UI labels, severity maps, CSS/HTML snippets
├── prompts.py                  # LLM prompt functions (one per tab)
├── utils.py                    # Shared helpers — model loader, exporters, retry logic
├── requirements.txt            # Python dependencies
├── .env                        # API keys (gitignored)
├── assets/
│   └── style.css               # Dark-theme overrides
└── ui/
    ├── __init__.py
    ├── tab_ambiguity.py        # Story Analyzer
    ├── tab_test_cases.py       # Test Cases
    ├── tab_bug_report.py       # Bug Report
    ├── tab_quality.py          # Quality Analytics
    ├── tab_automation.py       # Automation Script
    ├── tab_schema.py           # Schema Validator
    ├── tab_security.py         # Security Tests
    └── tab_performance.py      # Performance Tests
```

---

## 🎯 Notable Implementation Details

- **Structured output via Pydantic** — Every LLM response is parsed into a typed schema, not free-form text. This catches malformed outputs early and makes the UI rendering deterministic.
- **Tenacity-based retry** — Transient API failures are handled with exponential backoff before surfacing to the user.
- **Per-tab prompt isolation** — Each tab calls its own prompt function with no shared conversation history, which prevents cross-tab content leakage.
- **Session persistence** — Generated outputs survive browser refreshes via `st.session_state`.
- **Export-ready outputs** — Test cases export to CSV/Excel, bug reports to Markdown, automation projects to ZIP, k6 scripts to `.js`.

---



## 🛡️ Resilience & Error Handling

Recent improvements harden the app against real-world LLM failures:

| Layer | What It Does | Files |
|-------|-------------|-------|
| **Input Validation** | Length checks, suspicious-content detection, and total-size caps for every tab. | `validators.py` |
| **LLM Call Wrapping** | 3 automatic retries with exponential backoff. Errors classified as *transient* (network, rate limit) or *permanent* (auth, content policy). | `utils.py` |
| **JSON & Pydantic Resilience** | 5-stage JSON repair for malformed LLM outputs (markdown fences, unescaped quotes, prose wrappers). Falls back to raw JSON display if parsing still fails. | `json_repair_utils.py`, `utils.py` |
| **Display Fallbacks** | Every tab wraps its render logic in try/except. If the AI response parses but fails to render, users see the raw data + "Try Again" / "Report on GitHub" actions. | `ui/tab_*.py` |
| **Structured Logging** | JSON-structured error and success events for debugging. Session-state error tracking. | `utils.py` |
| **Plain-Text INVEST Scoring** | Replaced emoji-based status indicators (`✅ Pass / ⚠️ Partial / ❌ Fail`) with plain text (`PASS / PARTIAL / FAIL`) to eliminate cross-platform font/encoding issues. | `prompts.py`, `constants.py` |

---

## 🗺️ Roadmap

**v1.1 (in progress)** — addresses the highest-impact items from `IMPROVEMENTS.md`:
- Reduce false-positive validation findings in Schema Validator
- Add structured environment fields to Bug Report (eliminate hallucinated OS/build values)
- Add multi-sprint trend analysis to Quality Analytics
- Fix correlation gaps in Performance Tests k6 scripts
- Enforce JavaScript/TypeScript selection in Automation Script

**v2.0 (planned)** — production-readiness:
- Hosted demo on Streamlit Community Cloud
- Pytest-based regression suite covering all seven tabs
- Docker support

The full backlog is in (IMPROVEMENTS.md).




This is a personal project built for portfolio and learning purposes. Issues and feedback are welcome via GitHub Issues. PRs may not be merged but discussions are appreciated.

