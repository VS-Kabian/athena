"""URL liveness / fabrication detection (#4): classification, aggregation, caching."""
import pytest

from athena.agents import urlhealth
from athena.agents.urlhealth import _classify, summarize, check_urls, LIVE, DEAD, UNREACHABLE


async def _async_none(*a, **k):
    return None


async def _async_noop(*a, **k):
    return None


def test_classify_status_codes():
    assert _classify(200) == LIVE
    assert _classify(301) == LIVE
    assert _classify(403) == LIVE          # gated / rate-limited but the page exists
    assert _classify(429) == LIVE
    assert _classify(404) == DEAD          # gone -> fabricated/stale citation signal
    assert _classify(410) == DEAD
    assert _classify(500) == UNREACHABLE   # server error -> ambiguous/transient
    assert _classify(None) == UNREACHABLE


def test_summarize_counts_and_bad_list():
    results = {"https://a": {"status": LIVE, "code": 200},
               "https://b": {"status": DEAD, "code": 404},
               "https://c": {"status": UNREACHABLE, "code": None}}
    s = summarize(results)
    assert s["total"] == 3 and s["live"] == 1 and s["dead"] == 1 and s["unreachable"] == 1
    assert set(s["bad"]) == {"https://b", "https://c"}


@pytest.mark.asyncio
async def test_check_urls_dedups_and_aggregates(monkeypatch):
    async def fake_probe(url, client):
        return {"status": LIVE, "code": 200} if "good" in url else {"status": DEAD, "code": 404}
    monkeypatch.setattr(urlhealth, "_probe", fake_probe)
    monkeypatch.setattr(urlhealth, "_is_safe_url", lambda u: True)
    monkeypatch.setattr(urlhealth.cache, "get_json", _async_none)
    monkeypatch.setattr(urlhealth.cache, "set_json", _async_noop)
    res = await check_urls(["https://good.com/a", "https://bad.com/x", "https://good.com/a"])
    assert len(res) == 2                                    # the duplicate is probed once
    assert res["https://good.com/a"]["status"] == LIVE
    assert res["https://bad.com/x"]["status"] == DEAD


@pytest.mark.asyncio
async def test_check_urls_uses_cache(monkeypatch):
    calls = {"probe": 0}
    async def fake_probe(url, client):
        calls["probe"] += 1
        return {"status": LIVE, "code": 200}
    async def cached(key):
        return {"status": DEAD, "code": 404}     # pretend a prior verdict is cached
    monkeypatch.setattr(urlhealth, "_probe", fake_probe)
    monkeypatch.setattr(urlhealth, "_is_safe_url", lambda u: True)
    monkeypatch.setattr(urlhealth.cache, "get_json", cached)
    monkeypatch.setattr(urlhealth.cache, "set_json", _async_noop)
    res = await check_urls(["https://x.com/a"])
    assert res["https://x.com/a"]["status"] == DEAD and calls["probe"] == 0   # served from cache


@pytest.mark.asyncio
async def test_blocked_url_is_unreachable(monkeypatch):
    monkeypatch.setattr(urlhealth, "_is_safe_url", lambda u: False)   # SSRF guard rejects it
    monkeypatch.setattr(urlhealth.cache, "get_json", _async_none)
    monkeypatch.setattr(urlhealth.cache, "set_json", _async_noop)
    res = await check_urls(["http://169.254.169.254/latest/meta-data"])
    assert res["http://169.254.169.254/latest/meta-data"]["status"] == UNREACHABLE
