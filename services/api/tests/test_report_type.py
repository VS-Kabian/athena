from athena.agents.synthesizer import _system_prompt, SYS


def test_known_report_type_selects_template():
    p = _system_prompt("comparison")
    assert "compar" in p.lower() and p != SYS


def test_each_known_type_differs_from_standard():
    for rt in ("literature-review", "comparison", "how-to", "market-scan"):
        assert _system_prompt(rt) != SYS


def test_unknown_or_none_report_type_falls_back_to_standard():
    assert _system_prompt("nonsense") == SYS
    assert _system_prompt(None) == SYS
    assert _system_prompt("standard") == SYS
