"""P2-7 pure metric math: RAGAS faithfulness + ALCE citation precision/recall + the regression gate.
All offline — synthetic verdicts/counts, no DB, no model. Criteria that require a LIVE run (the model
judging real claims, the per-citation 'necessary' ablation) are documented in metrics.py and exercised
only by the harness, NOT here."""
from athena.eval.metrics import faithfulness, faithfulness_from_verdicts, citation_precision_recall
from athena.eval.harness import regression_gate


def _v(verdict, **kw):
    return {"verdict": verdict, **kw}


# ── faithfulness (RAGAS) ──
def test_faithfulness_all_supported_is_one():
    assert faithfulness(supported=5, total=5) == 1.0


def test_faithfulness_half_supported():
    assert faithfulness(supported=2, total=4) == 0.5


def test_faithfulness_no_claims_is_vacuously_one():
    assert faithfulness(supported=0, total=0) == 1.0     # nothing claimed -> nothing unfaithful


def test_faithfulness_refuted_and_nei_drag_it_down():
    assert faithfulness(supported=1, total=3) == round(1 / 3, 4)


def test_faithfulness_from_verdicts_matches_counts():
    vs = [_v("supported"), _v("supported"), _v("refuted"), _v("nei")]
    assert faithfulness_from_verdicts(vs) == 0.5


# ── ALCE citation precision / recall ──
def test_cpr_all_supported_is_perfect():
    assert citation_precision_recall([_v("supported"), _v("supported")]) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_cpr_recall_counts_unsupported_cited_claims():
    r = citation_precision_recall([_v("supported"), _v("nei"), _v("refuted"), _v("supported")])
    assert r["recall"] == 0.5                            # 2 of 4 cited claims are entailed by their citations


def test_cpr_precision_uses_necessary_flag_when_present():
    r = citation_precision_recall([_v("supported", necessary=True), _v("supported", necessary=False)])
    assert r["recall"] == 1.0 and r["precision"] == 0.5  # a superfluous citation lowers precision


def test_cpr_no_cited_claims_is_vacuously_one():
    assert citation_precision_recall([])["f1"] == 1.0
    assert citation_precision_recall([{"verdict": "nei", "cited": False}])["recall"] == 1.0


def test_cpr_values_bounded_unit_interval():
    r = citation_precision_recall([_v("supported"), _v("refuted"), _v("nei")])
    assert all(0.0 <= r[k] <= 1.0 for k in ("precision", "recall", "f1"))


# ── regression gate (pure; takes the compare_to_previous shape) ──
def test_gate_passes_with_no_previous_batch():
    assert regression_gate({"latest": {"faith": 0.9, "risk": 0.1}, "previous": None})["ok"]


def test_gate_fails_on_faithfulness_drop():
    g = regression_gate({"latest": {"faith": 0.70, "risk": 0.1}, "previous": {"faith": 0.90, "risk": 0.1}})
    assert not g["ok"] and any("faithfulness" in r for r in g["reasons"])


def test_gate_fails_on_risk_rise():
    assert not regression_gate({"latest": {"faith": 0.9, "risk": 0.30}, "previous": {"faith": 0.9, "risk": 0.10}})["ok"]


def test_gate_tolerates_small_noise():
    assert regression_gate({"latest": {"faith": 0.89, "risk": 0.11}, "previous": {"faith": 0.90, "risk": 0.10}})["ok"]
