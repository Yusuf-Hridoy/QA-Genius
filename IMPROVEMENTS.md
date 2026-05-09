# QA-Genius — Project Improvement Suggestions

> Living document tracking the state of the QA-Genius codebase.
> Current stack: Streamlit + LangChain + Google GenAI + Pydantic + Pandas

---

## Table of Contents

1. [Completed ✅](#-completed)
2. [Code Quality & Architecture](#-medium-priority--code-quality--architecture)
3. [Features & UX](#-features--ux-improvements)
4. [DevOps, Testing & Reliability](#-devops-testing--reliability)
5. [Performance & Scalability](#-performance--scalability)
6. [Quick Wins Checklist](#-quick-wins-checklist)

---

## ✅ Completed

| # | Area | Status |
|---|------|--------|
| 1 | **Modular Architecture** | ✅ Split from monolith into `app.py`, `models.py`, `prompts.py`, `utils.py`, `constants.py`, and `ui/` package |
| 2 | **Retry Logic** | ✅ `tenacity` with exponential backoff on transient API failures |
| 3 | **External CSS** | ✅ All styles moved to `assets/style.css` and loaded once at startup |
| 4 | **Session Persistence** | ✅ `st.session_state` preserves outputs across reruns in every tab |
| 5 | **Excel Export** | ✅ Test Cases tab exports `.xlsx` via `openpyxl` |
| 6 | **Bug Report Export** | ✅ Download buttons for Markdown and JSON formats |
| 7 | **JSON Repair** | ✅ Robust `json_repair` library handles malformed LLM JSON output |
| 8 | **Constants & Mappings** | ✅ `constants.py` centralizes badges, severity orders, and UI strings |
| 9 | **Dark Theme UI** | ✅ Polished dark mode with custom CSS, stat tiles, and scroll-to-top button |
| 10 | **Security & Performance Tabs** | ✅ Full `tab_security.py` and `tab_performance.py` modules with exports |

---


## 🟢 Features & UX Improvements

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 20 | **No Copy-to-Clipboard** | Code snippets in Automation & Performance tabs require manual selection. | Add copy-to-clipboard buttons for generated scripts. |
| 21 | **No JSON Pretty-Print Helper** | In Schema Validator, users may paste minified JSON. | Add a "Format JSON" button that pretty-prints the input before validation. |
| 22 | **No Bulk / File Upload** | Every tab only supports single manual text input. | Add file upload support (`.txt`, `.md`, `.json`) so users can batch-process requirements or responses. |
| 23 | **Forced Dark Theme** | The CSS forces a dark palette; users on light OS themes get no choice. | Respect `st.theme` or add a theme toggle in the sidebar. |
| 24 | **No Regenerate / Refine** | If the LLM output is slightly off, the user must manually edit the entire prompt and resubmit. | Add "Regenerate" and "Refine" buttons that tweak the prompt (e.g., "make it more detailed") automatically. |
| 25 | **No Streaming Output** | Users watch a generic spinner while the LLM thinks. | Implement streaming tokens if the LangChain model supports it, or show a progress indicator. |

---

## 🔵 DevOps, Testing & Reliability

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 26 | **Zero Unit Tests** | There is no test suite. Refactoring is risky. | Add `pytest` tests for:<br>- Pydantic model validation<br>- Prompt template rendering<br>- Utility functions (JSON formatting, badge mapping) |
| 27 | **No Logging** | There is no audit trail or debug logging for production issues. | Replace bare `st.error()` with Python's `logging` module; log prompts, errors, and latency. |
| 28 | **Loose Dependency Versions** | `requirements.txt` uses `>=` which can pull breaking updates. | Pin exact versions and add a `requirements-dev.txt` for `pytest`, `black`, `ruff`, `mypy`. |
| 29 | **No Dockerfile** | Deployment depends on the host having Python and all system libs installed. | Add a `Dockerfile` and optionally `docker-compose.yml` for one-command deployment. |
| 30 | **No CI/CD Pipeline** | No automated linting, formatting, or testing on pull requests. | Add a GitHub Actions workflow (`.github/workflows/ci.yml`) running `ruff`, `mypy`, and `pytest`. |

---

## 🟣 Performance & Scalability

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 31 | **No Response Caching** | Identical prompts are re-sent to the LLM every time. | Cache LLM responses by hashing the prompt + model parameters (respect TTL to avoid stale data). |
| 32 | **CSS Re-injected Every Rerun** | The full `<style>` block is passed to `st.markdown` on every interaction. | Load CSS once via `st.html` or read from an external file conditionally. |
| 33 | **Large DataFrame Rerenders** | `st.dataframe` may re-render entirely on minor state changes. | Use `st.session_state` to cache the DataFrame and only rebuild when input changes. |

---

## ✅ Quick Wins Checklist

- [x] **Rename** `requirments.txt` → `requirements.txt`
- [x] **Add** `.gitignore` and `README.md`
- [x] **Add** API key startup validation
- [x] **Move** CSS to `assets/style.css`
- [x] **Add** `st.session_state` to preserve outputs across reruns
- [x] **Add** Excel export for test cases
- [x] **Add** download buttons for Bug Report (Tab 2)
- [x] **Add** `tenacity` retry logic for API calls
- [ ] **Add** a "Format JSON" helper in Tab 5
- [ ] **Add** copy-to-clipboard for generated scripts
- [ ] **Pin** exact dependency versions
- [ ] **Add** `pytest` unit tests
- [ ] **Add** input length validators

---

## 📁 Current Project Structure

```
qa-genius/
├── assets/
│   └── style.css
├── ui/
│   ├── __init__.py
│   ├── tab_ambiguity.py
│   ├── tab_automation.py
│   ├── tab_bug_report.py
│   ├── tab_performance.py
│   ├── tab_quality.py
│   ├── tab_schema.py
│   ├── tab_security.py
│   └── tab_test_cases.py
├── .env
├── .gitignore
├── app.py
├── constants.py
├── models.py
├── prompts.py
├── requirements.txt
├── utils.py
├── IMPROVEMENTS.md
├── PROGRESS.md
├── README.md
└── ROADMAP.md
```

---

*Feel free to check items off as you implement them. If you need help implementing any specific improvement, just ask!*
