import pytest, respx, httpx
from athena.gateway.registry import list_providers, list_models

def test_list_providers_includes_core():
    ids = {p["id"] for p in list_providers()}
    assert {"gemini", "groq", "deepseek", "ollama"} <= ids

@pytest.mark.asyncio
@respx.mock
async def test_list_models_groq_dynamic():
    respx.get("https://api.groq.com/openai/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "llama-3.3-70b"}, {"id": "qwen-2.5-32b"}]}))
    models = await list_models("groq", api_key="k")
    assert "llama-3.3-70b" in models and "qwen-2.5-32b" in models

@pytest.mark.asyncio
async def test_list_models_falls_back_to_static_without_key():
    models = await list_models("gemini", api_key=None)
    assert any("gemini" in m for m in models)
