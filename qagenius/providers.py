"""Provider table: every provider is called with the `openai` client via its base_url."""

PROVIDERS: list[dict[str, str]] = [
    {
        "id": "gemini",
        "name": "Google Gemini (free)",
        "short": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.8-flash",
        "key_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "groq",
        "name": "Groq (free)",
        "short": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
    },
    {
        "id": "openai",
        "name": "OpenAI (GPT)",
        "short": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
    },
    {
        "id": "xai",
        "name": "xAI (Grok)",
        "short": "Grok",
        "base_url": "https://api.x.ai/v1",
        "model": "grok-3-mini",
        "key_url": "https://console.x.ai",
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "short": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "model": "mistral-small-latest",
        "key_url": "https://console.mistral.ai/api-keys",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "short": "Claude",
        "base_url": "https://api.anthropic.com/v1/",
        "model": "claude-haiku-4-5",
        "key_url": "https://console.anthropic.com/settings/keys",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "short": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-3.8-flash",
        "key_url": "https://openrouter.ai/keys",
    },
]

BY_ID: dict[str, dict[str, str]] = {p["id"]: p for p in PROVIDERS}


def get_provider(provider_id: str) -> dict[str, str] | None:
    return BY_ID.get(provider_id)
