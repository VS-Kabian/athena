"""Model ladder: role -> model resolution with graceful fallback (Upgrade 5)."""
from athena.gateway.ladder import for_role

MAIN = {"provider": "deepseek", "model": "deepseek-reasoner", "api_key": "m"}
FAST = {"provider": "deepseek", "model": "deepseek-chat", "api_key": "f"}
VERIF = {"provider": "gemini", "model": "gemini-2.5-pro", "api_key": "v"}


def test_synthesis_uses_main():
    assert for_role("synthesis", MAIN, FAST, VERIF) is MAIN
    assert for_role("draft", MAIN, FAST, VERIF) is MAIN


def test_cheap_roles_use_fast_when_available():
    for role in ("plan", "triage", "extract", "relevance", "links", "outline"):
        assert for_role(role, MAIN, FAST, VERIF) is FAST, role


def test_entail_prefers_verifier_then_fast_then_main():
    assert for_role("entail", MAIN, FAST, VERIF) is VERIF
    assert for_role("entail", MAIN, FAST) is FAST
    assert for_role("entail", MAIN) is MAIN


def test_cheap_roles_fall_back_to_main_without_fast():
    assert for_role("plan", MAIN) is MAIN
    assert for_role("triage", MAIN, None, VERIF) is MAIN


def test_verify_prefers_verifier_then_fast_then_main():
    assert for_role("verify", MAIN, FAST, VERIF) is VERIF
    assert for_role("verify", MAIN, FAST) is FAST
    assert for_role("verify", MAIN) is MAIN


def test_unknown_role_defaults_to_cheap_tier():
    assert for_role("something-new", MAIN, FAST) is FAST
    assert for_role("something-new", MAIN) is MAIN


def test_entail_judge_is_model_agnostic():
    """Model-agnostic routing guard (criterion 4): the entailment judge must NOT depend on which
    synthesis model the user picks — swapping the main `llm` leaves the chosen judge identical — and a
    configured verifier is always preferred over the synthesis model. This is what makes the trust score
    behave the same whichever model is selected, so risk can't drift just because the frontier model did."""
    MAIN_A = {"provider": "deepseek", "model": "deepseek-reasoner", "api_key": "a"}
    MAIN_B = {"provider": "openai", "model": "gpt-4o", "api_key": "b"}
    # a verifier is configured -> same judge regardless of the synthesis model, and it IS the verifier
    assert for_role("entail", MAIN_A, FAST, VERIF) is for_role("entail", MAIN_B, FAST, VERIF)
    assert for_role("entail", MAIN_A, FAST, VERIF) is VERIF      # prefers the independent verifier
    # no verifier but a fast tier -> judge is still identical across different synthesis models
    assert for_role("entail", MAIN_A, FAST) is for_role("entail", MAIN_B, FAST) is FAST
