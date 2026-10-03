# QA-Genius v2
FastAPI + HTMX rewrite of QA-Genius (v2 branch).
Old Streamlit app lives on `main` and is untouched.
Phase 1: sidebar, keys page, story check, load example.
Live URL: TBD

## Troubleshooting
- `python scripts/check_key.py` checks one provider key with a tiny JSON
  request. It asks for the provider id and the key (hidden while typing)
  and prints `OK <provider> <model>` or the cleaned error. The key is
  never printed.
