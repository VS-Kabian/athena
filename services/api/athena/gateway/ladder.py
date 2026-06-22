"""Model ladder — resolve which configured model serves each role.

The user configures up to three model specs: ``llm`` (main/frontier), ``llm_fast`` (optional cheap
model), and ``verifier`` (optional independent checker). Deep research fires many cheap, high-volume
calls (planning, triage, link ranking, per-section outlining, entailment) plus a few expensive ones
(final synthesis). Routing each call to the right tier keeps cost/latency down and reserves the
frontier model for the work that needs it — the way Perplexity/Gemini route per task.

Every resolver degrades gracefully: a missing fast/verifier model falls back down the chain to the
main model, so a single configured model still works everywhere.
"""

# roles that should use the strong (frontier) model — quality matters more than cost
_FRONTIER = frozenset({"synthesis", "draft"})
# roles best served by an independent checker model when one is configured
_CHECK = frozenset({"verify", "entail"})


def for_role(role: str, llm: dict, fast: dict | None = None, verifier: dict | None = None) -> dict:
    """Return the llm spec to use for ``role``.

    - ``synthesis`` / ``draft``      -> main (frontier)
    - ``verify``                     -> verifier, else fast, else main
    - everything else (``plan`` / ``triage`` / ``extract`` / ``relevance`` / ``links`` /
      ``outline`` / ``entail``)      -> fast, else main  (the cheap tier)
    """
    if role in _FRONTIER:
        return llm
    if role in _CHECK:
        return verifier or fast or llm
    return fast or llm
