from athena.embed import cosine, top_k

def test_cosine_identical_and_orthogonal():
    assert abs(cosine([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-9
    assert abs(cosine([1, 0, 0], [0, 1, 0])) < 1e-9
    assert cosine([0, 0], [1, 1]) == 0.0

def test_top_k_orders_by_similarity():
    items = [{"v": [1, 0]}, {"v": [0, 1]}, {"v": [0.9, 0.1]}]
    res = top_k([1, 0], items, key=lambda x: x["v"], k=2)
    assert res[0]["v"] == [1, 0] and res[1]["v"] == [0.9, 0.1]

def test_embed_returns_384_dims():
    from athena.embed import embed_passages
    v = embed_passages(["retrieval augmented generation"])
    assert len(v) == 1 and len(v[0]) == 384
