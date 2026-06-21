"""Regression tests for audit fixes F-003, F-013, F-016, F-017 (engine-owned set).

F-003 — PDF render must surface pisa errors instead of returning partial/empty bytes.
F-013 — verifier correction must target the specific cited-sentence occurrence by position,
         not the first textual match (so duplicate/substring claims aren't mis-rewritten).
F-016 — the dead `event_bus` / ATHENA_EVENT_BUS setting is removed from config.
F-017 — the run concurrency semaphore reads settings.max_concurrent_runs (single source of truth).
"""
import pytest
from unittest.mock import patch


# ── F-003: pisa error status -> RuntimeError, never silent partial bytes ──
def test_to_pdf_bytes_raises_on_pisa_error():
    import athena.report.export as export

    class _ErrStatus:
        err = 1

    # patch CreatePDF to report a render error (and write nothing useful to the buffer)
    with patch("athena.report.export.pisa.CreatePDF", return_value=_ErrStatus()):
        with pytest.raises(RuntimeError):
            export.to_pdf_bytes("# Hello\n\nWorld")


def test_to_pdf_bytes_ok_on_success():
    # the real renderer (no patch) must still yield a valid PDF, status.err == 0
    from athena.report.export import to_pdf_bytes
    assert to_pdf_bytes("# Hello\n\nWorld")[:4] == b"%PDF"


# ── F-013: correction targets the verdict's sentence by position, not first match ──
@pytest.mark.asyncio
async def test_correction_targets_the_intended_duplicate_occurrence():
    # two IDENTICAL cited sentences; only the SECOND (n=2) is contradicted.
    from athena.agents.verifier import verify_report

    md = ("# R\n\n## Findings\n"
          "The sky is green [1]. The sky is green [1].\n\n## Sources\n\n1. a\n")
    src = ["The sky is blue."]
    llm = {"provider": "groq", "model": "m", "api_key": "k"}

    async def fake(*a, **k):
        # n=1 supported (untouched), n=2 contradicted -> rewrite ONLY the second occurrence
        return ('[{"n":1,"verdict":"supported","correction":""},'
                ' {"n":2,"verdict":"contradicted","correction":"The sky is blue [2nd]."}]')

    with patch("athena.agents.verifier.complete", side_effect=fake):
        out, contested = await verify_report(md, src, llm)

    # the corrected text appears exactly once, in the second slot
    assert "The sky is blue [2nd]." in out
    # the FIRST occurrence is left intact (it was 'supported'); exactly one green sentence remains
    assert out.count("The sky is green [1].") == 1
    # and the surviving green sentence precedes the correction (i.e. the first one was kept)
    assert out.index("The sky is green [1].") < out.index("The sky is blue [2nd].")
    assert any("corrected" in c.lower() for c in contested)


@pytest.mark.asyncio
async def test_two_corrections_apply_independently_without_interference():
    # both identical sentences contradicted, with DIFFERENT corrections -> each lands in its own slot
    from athena.agents.verifier import verify_report

    md = ("# R\n\n## Findings\n"
          "Value is ten [1]. Value is ten [1].\n\n## Sources\n\n1. a\n")
    src = ["The value is one."]
    llm = {"provider": "groq", "model": "m", "api_key": "k"}

    async def fake(*a, **k):
        return ('[{"n":1,"verdict":"contradicted","correction":"Value is one [1]."},'
                ' {"n":2,"verdict":"contradicted","correction":"Value is two [1]."}]')

    with patch("athena.agents.verifier.complete", side_effect=fake):
        out, _ = await verify_report(md, src, llm)

    assert "Value is one [1]." in out and "Value is two [1]." in out
    assert "Value is ten [1]." not in out
    assert out.index("Value is one [1].") < out.index("Value is two [1].")


# ── F-016: the dead event_bus config field is gone ──
def test_event_bus_setting_removed():
    from athena.config import settings, Settings
    assert not hasattr(settings, "event_bus")
    assert "event_bus" not in Settings.model_fields


# ── F-017: semaphore bound comes from settings.max_concurrent_runs (single source of truth) ──
@pytest.mark.asyncio
async def test_semaphore_reads_settings_max_concurrent_runs(monkeypatch):
    from athena import runner
    from athena.config import settings

    monkeypatch.setattr(runner, "_sem", None)          # force a fresh build
    monkeypatch.setattr(settings, "max_concurrent_runs", 7, raising=False)

    sem = runner.semaphore()
    assert sem._value == 7                              # honors the configured (e.g. .env-set) limit
    assert runner.semaphore() is sem                   # still a singleton within the run
