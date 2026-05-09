# QA-Genius — Project Improvement Suggestions

> Generated after scanning the codebase on 2026-04-28.
> Current stack: Streamlit + LangChain + Google GenAI + Pydantic + Pandas

---

## Table of Contents

1. [Critical / High Priority](#-critical--high-priority)
2. [Code Quality & Architecture](#-medium-priority--code-quality--architecture)
3. [Features & UX](#-features--ux-improvements)
4. [DevOps, Testing & Reliability](#-devops-testing--reliability)
5. [Performance & Scalability](#-performance--scalability)
6. [Quick Wins Checklist](#-quick-wins-checklist)

---

## 🔴 Critical / High Priority

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 1 | **File Name Typo** | `requirments.txt` is misspelled (missing the first **i**). | Rename to `requirements.txt`. |
| 2 | **Monolithic Codebase** | The entire app lives in a single `qa.py` (875 lines). UI, prompts, business logic, and Pydantic models are all tightly coupled. | Split into a modular structure:<br>`models.py` → Pydantic schemas<br>`prompts.py` → LLM prompt templates<br>`utils.py` → shared helpers<br>`ui/` → tab components<br>`app.py` → entry point & layout |
| 3 | **Missing README** | There is no `README.md`. Anyone cloning the repo won't know how to install or run the app. | Add a `README.md` with setup steps, environment variables, dependency installation, and screenshots/GIFs. |
| 4 | **Missing `.gitignore`** | The project root has no `.gitignore`. `.env` and `.venv/` could accidentally be committed. | Add a `.gitignore` excluding `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `.streamlit/`, etc. |
| 5 | **No API Key Validation** | If `GOOGLE_API_KEY` is missing or invalid, the app will crash with a confusing traceback. | Add a startup guard that checks for the key and shows a friendly `st.error()` with setup instructions. |
| 6 | **No Retry Logic** | Transient API failures (rate limits, timeouts) result in a hard error for the user. | Integrate `tenacity` to retry with exponential backoff on `ResourceExhausted` or `ServiceUnavailable`. |

---

## 🟡 Medium Priority — Code Quality & Architecture

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 7 | **Inline CSS Bloat** | ~230 lines of raw CSS and HTML are embedded as Python strings, making the file hard to read and maintain. | Move all CSS into a dedicated `assets/style.css` file and load it once at startup. |
| 8 | **No Type Hints** | Functions like `load_model()` lack return type annotations. | Add type hints (e.g., `def load_model() -> ChatGoogleGenerativeAI:`). |
| 9 | **No Docstrings** | There is zero documentation for what each tab, function, or model represents. | Add Google-style or NumPy-style docstrings to every public function and Pydantic model. |
| 10 | **Bare Exception Handling** | Every tab uses `except Exception as e: st.error(f"Parsing error: {e}")`. This swallows valuable debugging info and handles everything the same way. | Catch specific exceptions:<br>- `json.JSONDecodeError` for invalid JSON<br>- `OutputParserException` for LLM parsing failures<br>- `GoogleAPIError` for API issues |
| 11 | **Magic Strings Everywhere** | Badge CSS classes, severity labels, and priority strings are hardcoded and repeated across tabs. | Create a `constants.py` with enums or dictionaries (e.g., `SEVERITY_BADGE_MAP`, `PRIORITY_ORDER`). |
| 12 | **Plain Strings Instead of Enums** | Fields like `severity`, `priority`, and `reproducibility_rate` accept any string value from the LLM. | Convert them to `enum.StrEnum` so Pydantic validates allowed values automatically. |
| 13 | **Hardcoded Model & Temperature** | `google model` and `temperature=0.3` are hardcoded with no user control. | Add a sidebar or settings panel to let users select the model and adjust creativity/precision. |

---

## 🟢 Features & UX Improvements

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 14 | **No Session History** | Refreshing the browser loses all generated test cases, bug reports, and scripts. | Use `st.session_state` to persist outputs across reruns. Consider a "Clear History" button. |
| 15 | **No Excel Export** | Tab 1 (Test Cases) only supports CSV download. QA teams often prefer `.xlsx` with formatting. | Add `.xlsx` export using `openpyxl` with styled headers and auto-width columns. |
| 16 | **No Copy-to-Clipboard** | Code snippets in Tab 4 require manual selection. | Add copy-to-clipboard buttons for generated scripts using `st.code` + a small JS snippet, or a dedicated copy helper. |
| 17 | **No JSON Pretty-Print Helper** | In Tab 5, users may paste minified JSON. | Add a "Format JSON" button that pretty-prints the input before validation. |
| 18 | **No Bulk / File Upload** | Every tab only supports single manual text input. | Add file upload support (`.txt`, `.md`, `.json`) so users can batch-process requirements or responses. |
| 19 | **Forced Dark Theme** | The CSS forces a dark palette; users on light OS themes get no choice. | Respect `st.theme` or add a theme toggle in the sidebar. |
| 20 | **Missing Export for Bug Report** | Tab 2 displays a formatted bug report but offers no download option. | Add export buttons for Markdown and JSON formats. |
| 21 | **No Regenerate / Refine** | If the LLM output is slightly off, the user must manually edit the entire prompt and resubmit. | Add "Regenerate" and "Refine" buttons that tweak the prompt (e.g., "make it more detailed") automatically. |

---

## 🔵 DevOps, Testing & Reliability

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 22 | **Zero Unit Tests** | There is no test suite. Refactoring is risky. | Add `pytest` tests for:<br>- Pydantic model validation<br>- Prompt template rendering<br>- Utility functions (JSON formatting, badge mapping) |
| 23 | **No Input Sanitization** | Raw user input is injected directly into LLM prompts without length or content checks. | Add max-length validators and strip dangerous characters to prevent prompt injection. |
| 24 | **No Logging** | There is no audit trail or debug logging for production issues. | Replace bare `st.error()` with Python's `logging` module; log prompts, errors, and latency. |
| 25 | **Loose Dependency Versions** | `requirements.txt` uses `>=` which can pull breaking updates. | Pin exact versions and add a `requirements-dev.txt` for `pytest`, `black`, `ruff`, `mypy`. |
| 26 | **No Dockerfile** | Deployment depends on the host having Python and all system libs installed. | Add a `Dockerfile` and optionally `docker-compose.yml` for one-command deployment. |
| 27 | **No CI/CD Pipeline** | No automated linting, formatting, or testing on pull requests. | Add a GitHub Actions workflow (`.github/workflows/ci.yml`) running `ruff`, `mypy`, and `pytest`. |

---

## 🟣 Performance & Scalability

| # | Area | Issue | Suggested Fix |
|---|------|-------|---------------|
| 28 | **No Response Caching** | Identical prompts are re-sent to the LLM every time. | Cache LLM responses by hashing the prompt + model parameters (respect TTL to avoid stale data). |
| 29 | **No Streaming Output** | Users watch a generic spinner while the LLM thinks. | Implement streaming tokens if the LangChain model supports it, or show a progress indicator. |
| 30 | **CSS Re-injected Every Rerun** | The full `<style>` block is passed to `st.markdown` on every interaction. | Load CSS once via `st.html` or read from an external file conditionally. |
| 31 | **Large DataFrame Rerenders** | `st.dataframe` may re-render entirely on minor state changes. | Use `st.session_state` to cache the DataFrame and only rebuild when input changes. |

---

## ✅ Quick Wins Checklist

If you want immediate impact with minimal effort, tackle these first:

- [ ] **Rename** `requirments.txt` → `requirements.txt`
- [ ] **Add** `.gitignore` and `README.md`
- [ ] **Add** API key startup validation
- [ ] **Move** CSS to `assets/style.css`
- [ ] **Add** `st.session_state` to preserve outputs across reruns
- [ ] **Add** Excel export for test cases
- [ ] **Add** download buttons for Bug Report (Tab 2)
- [ ] **Add** a "Format JSON" helper in Tab 5
- [ ] **Add** `tenacity` retry logic for API calls
- [ ] **Pin** exact dependency versions

---

## 📁 Suggested Project Structure

```
qa-genius/
├── .github/
│   └── workflows/
│       └── ci.yml
├── assets/
│   └── style.css
├── src/
│   ├── __init__.py
│   ├── app.py              # Entry point (replaces qa.py)
│   ├── models.py           # All Pydantic models
│   ├── prompts.py          # ChatPromptTemplate definitions
│   ├── constants.py        # Enums, mappings, config
│   └── utils.py            # Helpers (formatters, exporters, validators)
├── ui/
│   ├── __init__.py
│   ├── tab_test_cases.py
│   ├── tab_bug_report.py
│   ├── tab_quality.py
│   ├── tab_automation.py
│   └── tab_schema.py
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   └── test_utils.py
├── .env.example
├── .gitignore
├── Dockerfile
├── README.md
├── requirements.txt
└── requirements-dev.txt
```

---

*Feel free to check items off as you implement them. If you need help implementing any specific improvement, just ask!*
