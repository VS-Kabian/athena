import httpx

PROVIDERS = {
    "gemini":   {"label": "Google Gemini", "needs_key": True,
                 "models_url": "https://generativelanguage.googleapis.com/v1beta/models",
                 "static": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
                 "litellm_prefix": "gemini/"},
    "groq":     {"label": "Groq", "needs_key": True,
                 "models_url": "https://api.groq.com/openai/v1/models",
                 "static": ["llama-3.3-70b-versatile", "qwen-2.5-32b"],
                 "litellm_prefix": "groq/"},
    "deepseek": {"label": "DeepSeek", "needs_key": True,
                 "models_url": "https://api.deepseek.com/models",
                 "static": ["deepseek-chat", "deepseek-reasoner"],
                 "litellm_prefix": "deepseek/"},
    "ollama":   {"label": "Ollama (local)", "needs_key": False,
                 "models_url": "http://localhost:11434/api/tags",
                 "static": ["llama3.1", "qwen2.5"],
                 "litellm_prefix": "ollama/"},
}

def list_providers():
    return [{"id": k, "label": v["label"], "needs_key": v["needs_key"]} for k, v in PROVIDERS.items()]

def _parse_models(provider: str, data: dict) -> list[str]:
    if provider == "ollama":
        return [m["name"] for m in data.get("models", [])]
    if provider == "gemini":
        return [m["name"].split("/")[-1] for m in data.get("models", [])]
    return [m["id"] for m in data.get("data", [])]

async def list_models(provider: str, api_key: str | None) -> list[str]:
    cfg = PROVIDERS[provider]
    if cfg["needs_key"] and not api_key:
        return cfg["static"]
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = cfg["models_url"]
    if provider == "gemini" and api_key:
        # send the key in a header, NEVER the URL query string — query strings leak into access
        # logs, proxies, and exception/`raise_for_status` messages.
        headers = {"x-goog-api-key": api_key}
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url, headers=headers)
            r.raise_for_status()
            models = _parse_models(provider, r.json())
            return models or cfg["static"]
    except Exception:
        return cfg["static"]

def litellm_model(provider: str, model: str) -> str:
    return PROVIDERS[provider]["litellm_prefix"] + model
