import pytest, respx, httpx
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_mcp_server_registers_research_tools():
    from athena.mcp import server
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert {"deep_research", "get_report"} <= names


@pytest.mark.asyncio
async def test_mcp_server_registers_skill_tools():
    """rerank + verify are exposed as MCP tools so the ADK agent can attach them as skills."""
    from athena.mcp import server
    names = {t.name for t in await server.mcp.list_tools()}
    assert {"rerank_sources", "verify_claims"} <= names


@pytest.mark.asyncio
@respx.mock
async def test_rerank_sources_tool_calls_engine():
    from athena.mcp import server
    respx.post("http://localhost:7000/api/rerank").mock(return_value=httpx.Response(
        200, json={"ranked": [{"index": 0, "text": "a", "score": 1.2}], "count": 1}))
    out = await server.rerank_sources("q", ["a", "b"], top_k=1)
    assert out["ranked"][0]["text"] == "a" and out["count"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_verify_claims_tool_calls_engine():
    from athena.mcp import server
    respx.post("http://localhost:7000/api/verify").mock(return_value=httpx.Response(
        200, json={"report_markdown": "ok [1]", "contested": [], "flagged": 0}))
    out = await server.verify_claims("report [1]", [{"text": "s"}])
    assert out["flagged"] == 0 and out["report_markdown"] == "ok [1]"


@pytest.mark.asyncio
@respx.mock
async def test_skill_tools_return_error_dict_on_failure():
    from athena.mcp import server
    respx.post("http://localhost:7000/api/rerank").mock(return_value=httpx.Response(500, text="boom"))
    out = await server.rerank_sources("q", ["a"])
    assert "error" in out and "500" in out["error"]


@pytest.mark.asyncio
@respx.mock
async def test_deep_research_starts_run_polls_and_returns_report():
    from athena.mcp import server
    respx.post("http://localhost:7000/api/research").mock(
        return_value=httpx.Response(200, json={"run_id": "r1"}))
    respx.get("http://localhost:7000/api/research/r1").mock(return_value=httpx.Response(200, json={
        "run": {"status": "done", "quality_score": 80}, "report": "# Report body [1]",
        "sources": [{"title": "Primary", "url": "https://docs.x.com", "validated": True}]}))
    with patch("athena.mcp.server.asyncio.sleep", AsyncMock()):   # don't actually wait between polls
        out = await server.deep_research("topic", provider="groq", model="m", rounds=1)
    assert out["run_id"] == "r1" and out["status"] == "done"
    assert out["quality_score"] == 80 and out["report_markdown"].startswith("# Report")
    assert out["top_sources"][0]["url"] == "https://docs.x.com"


@pytest.mark.asyncio
@respx.mock
async def test_deep_research_returns_error_dict_on_backend_failure():
    from athena.mcp import server
    respx.post("http://localhost:7000/api/research").mock(return_value=httpx.Response(500, text="boom"))
    out = await server.deep_research("topic")
    assert "error" in out and "500" in out["error"]   # structured error, never raises
