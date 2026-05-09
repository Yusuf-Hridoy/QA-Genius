# 🧠 QA-Genius — SQA Intelligence Suite

An AI-powered Quality Assurance companion that turns user stories, API specs, and plain-text descriptions into production-grade test artifacts. Built for QA engineers, SDETs, and developers who want to ship with confidence.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B)
![GenAI](https://img.shields.io/badge/AI-Google%20GenAI-4285F4)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ What It Does

QA-Genius is a one-stop workspace for generating, analyzing, and exporting software quality artifacts using Large Language Models. Describe your feature, paste your JSON, or outline a user flow — the AI handles the rest.

| Module | Description |
|--------|-------------|
| 📝 **Story Analyzer** | Detects ambiguities, missing ACs, and inconsistencies in user stories before they reach development. |
| 🧪 **Test Cases** | Generates structured functional, edge-case, regression, and smoke test cases with steps, data, and expected results. |
| 🐛 **Bug Report** | Transforms raw bug notes into production-grade bug reports with severity, reproducibility, and environment details. |
| 📊 **Quality Analytics** | Analyzes sprint execution summaries and outputs a quality health score with actionable insights. |
| ⚙️ **Automation Script** | Scaffolds complete automation projects — test code, page objects, config, and a run-ready ZIP. |
| 🔍 **Schema Validator** | Validates JSON payloads against structural, semantic, and security best practices. |
| 🔒 **Security Tests** | Produces OWASP Top 10 mapped security test cases with real payloads, remediation steps, and tool hints. |
| ⚡ **Performance Tests** | Architects k6 performance suites with 6 load profiles (Smoke → Breakpoint), SLA assertions, and runnable scripts. |

---

## 🚀 Live Demo

```bash
streamlit run app.py
```

> The app launches with a dark-themed, wide-layout UI. Each tab is self-contained — no page reloads needed.

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Streamlit (custom CSS, responsive wide layout) |
| **AI / LLM** | LangChain + Google GenAI (`gemini-2.5-flash-lite`) |
| **Data Validation** | Pydantic v2 (structured output parsing) |
| **Data Processing** | Pandas, OpenPyXL (Excel export) |
| **Resilience** | Tenacity (exponential backoff retry) |
| **Config** | python-dotenv |

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

> Get your API key from [Google AI Studio](https://aistudio.google.com/app/apikey).

### 5. Run the app

```bash
streamlit run app.py
```

The app will open at `http://localhost:8501`.

---

## 📁 Project Structure

```
qa-genius/
├── app.py                      # Streamlit entry point — layout, tabs, theming
├── models.py                   # Pydantic schemas for all LLM outputs
├── constants.py                # UI labels, severity maps, CSS/HTML snippets
├── prompts.py                  # LLM prompt templates (one per module)
├── utils.py                    # Shared helpers — model loader, exporters, retry logic
├── requirements.txt            # Python dependencies
├── .env                        # API keys (gitignored)
├── assets/
│   └── style.css               # Custom dark-theme overrides
└── ui/
    ├── __init__.py
    ├── tab_ambiguity.py        # Story Analyzer tab
    ├── tab_test_cases.py       # Test Case Generator tab
    ├── tab_bug_report.py       # Bug Report Formatter tab
    ├── tab_quality.py          # Quality Analytics tab
    ├── tab_automation.py       # Automation Script tab
    ├── tab_schema.py           # Schema Validator tab
    ├── tab_security.py         # Security Tests tab
    └── tab_performance.py      # Performance Tests tab
```

---

## 🎯 Key Features

- **Structured AI Output** — Every generation is parsed into strongly-typed Pydantic models, not free-form text.
- **Export Ready** — Download test cases as CSV/Excel, bug reports as Markdown, automation projects as ZIP, and performance scripts as `.js`.
- **Retry & Resilience** — Built-in exponential backoff protects against transient API failures.
- **Dark-First UI** — Polished dark theme with custom CSS, stat tiles, badges, and scroll-to-top.
- **Session Persistence** — Generated outputs survive browser refreshes via `st.session_state`.
- **No Placeholders** — Automation and performance scripts are generated runnable; no `// TODO` or `fill in here`.

---

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | ✅ Yes | Google GenAI API key for LLM inference |

---

## 🗺️ Roadmap

See [`ROADMAP.md`](ROADMAP.md) for planned features and [`IMPROVEMENTS.md`](IMPROVEMENTS.md) for the detailed backlog.

High-level upcoming items:

- [ ] Docker support for one-command deployment
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Unit test suite (`pytest`)
- [ ] Response caching to reduce API costs
- [ ] Support for additional LLM providers (OpenAI, Anthropic)

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

> **Powered by AI** · Built with Streamlit & LangChain
