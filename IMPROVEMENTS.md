# QA-Genius — Project Improvement Suggestions

> Living document tracking the state of the QA-Genius codebase.
> Current stack: Streamlit + LangChain + Google GenAI + Pydantic + Pandas

---

## Table of Contents

1. [Completed ✅](#-completed)
2. [Critical / High Priority](#-critical--high-priority)
3. [Code Quality & Architecture](#-medium-priority--code-quality--architecture)
4. [Features & UX](#-features--ux-improvements)
5. [DevOps, Testing & Reliability](#-devops-testing--reliability)
6. [Performance & Scalability](#-performance--scalability)
7. [Quick Wins Checklist](#-quick-wins-checklist)

---

## ✅ Completed

| # | Area | Status |
|---|------|--------|
| 1 | **Modular Architecture** | ✅ Split from monolith into `app.py`, `models.py`, `prompts.py`, `utils.py`, `constants.py`, and `ui/` package |
| 2 | **README.md** | ✅ Professional README with install steps, env vars, project structure, and feature overview |
| 3 | **`.gitignore`** | ✅ Excludes `.env`, `.venv/`, `__pycache__/`, `.streamlit/`, local data files |
| 4 | **API Key Validation** | ✅ Startup guard checks `GOOGLE_API_KEY` and shows friendly `st.error()` with instructions |
| 5 | **Retry Logic** | ✅ `tenacity` with exponential backoff on transient API failures |
| 6 | **External CSS** | ✅ All styles moved to `assets/style.css` and loaded once at startup |
| 7 | **Session Persistence** | ✅ `st.session_state` preserves outputs across reruns in every tab |
| 8 | **Excel Export** | ✅ Test Cases tab exports `.xlsx` via `openpyxl` |
| 9 | **Bug Report Export** | ✅ Download buttons for Markdown and JSON formats |
| 10 | **JSON Repair** | ✅ Robust `json_repair` library handles malformed LLM JSON output |
| 11 | **Constants & Mappings** | ✅ `constants.py` centralizes badges, severity orders, and UI strings |
| 12 | **Dark Theme UI** | ✅ Polished dark mode with custom CSS, stat tiles, and scroll-to-top button |
| 13 | **Security & Performance Tabs** | ✅ Full `tab_security.py` and `tab_performance.py` modules with exports |

---

## 🔴 Critical / High Priority

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 14 | **Bare Exception Handling** | Every tab uses `except Exception as e: st.error(f"Parsing error: {e}")`. This swallows valuable debugging info and handles everything the same way. | Catch specific exceptions:<br>- `json.JSONDecodeError` for invalid JSON<br>- `OutputParserException` for LLM parsing failures<br>- `GoogleAPIError` for API issues |
| 15 | **Plain Strings Instead of Enums** | Fields like `severity`, `priority`, and `reproducibility_rate` accept any string value from the LLM. | Convert them to `enum.StrEnum` so Pydantic validates allowed values automatically. |

---

## 🟡 Medium Priority — Code Quality & Architecture

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 16 | **No Type Hints** | Some functions still lack return type annotations. | Add type hints to every public function and Pydantic model method. |
| 17 | **No Docstrings** | Tab render functions and complex utilities lack documentation. | Add Google-style or NumPy-style docstrings to public APIs. |
| 18 | **Hardcoded Model & Temperature** | `gemini-2.5-flash-lite` and `temperature=0.3` are hardcoded with no user control. | Add a sidebar or settings panel to let users select the model and adjust creativity/precision. |
| 19 | **Input Sanitization** | Raw user input is injected directly into LLM prompts without length or content checks. | Add max-length validators and strip dangerous characters to prevent prompt injection. |

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
