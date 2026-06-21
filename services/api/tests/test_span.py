from unittest.mock import patch

from athena.rag import select_span, split_sentences


def test_split_sentences_basic():
    s = split_sentences("First sentence here. Second one follows! Third question? Yes.")
    assert len(s) >= 3


def test_split_sentences_windows_long_runs():
    s = split_sentences("x" * 1000, max_len=400)
    assert len(s) == 3 and all(len(p) <= 400 for p in s)


def test_select_span_picks_most_relevant_sentence():
    text = ("The sky is blue today. Transformers use self-attention for sequence modeling. "
            "Cats are mammals.")

    def fake_rerank(q, passages):
        return [9.0 if "self-attention" in p else 0.0 for p in passages]

    with patch("athena.rag.rerank", side_effect=fake_rerank):
        span = select_span("how do transformers work", text)
    assert "self-attention" in span


def test_select_span_falls_back_to_embedding_when_rerank_unavailable():
    text = "Alpha statement about cars. Beta statement about quantum computing qubits."

    def emb_q(q):
        return [1.0, 0.0]

    def emb_p(passages):
        return [[0.0, 1.0] if "qubits" in p else [1.0, 0.0] for p in passages]

    with patch("athena.rag.rerank", return_value=[]), \
         patch("athena.rag.embed_query", side_effect=emb_q), \
         patch("athena.rag.embed_passages", side_effect=emb_p):
        span = select_span("cars", text)
    assert "cars" in span  # embedding picked the aligned sentence


def test_select_span_single_sentence_returns_leading_text():
    text = "Only one sentence with no terminal punctuation here"
    assert select_span("q", text).startswith("Only one sentence")


def test_select_span_empty_returns_empty():
    assert select_span("q", "") == ""
