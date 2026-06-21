import re
from ..embed import embed_query, embed_passages, cosine


def _sentences(markdown: str) -> list[str]:
    body = re.split(r"##\s*Sources", markdown)[0]
    body = re.sub(r"[#*`>_]", " ", body)
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [s.strip() for s in parts if len(s.strip()) > 25]


def factcheck(markdown: str, source_texts_in_order: list[str], threshold: float = 0.55) -> dict:
    """Verify each cited sentence against its cited source (embedding cosine) AND check
    cross-source corroboration — how many *independent* sources support the claim. Claims backed
    by only one source are listed in ``single_source`` (weak consensus); ``consensus`` is the
    fraction of claims supported by >=2 sources. risk = unsupported / total."""
    sents = _sentences(markdown)
    cited = [s for s in sents if re.search(r"\[\d+\]", s)]
    target = cited if cited else sents
    nsrc = len(source_texts_in_order)
    cache: dict[int, list] = {}

    def _emb(idx: int) -> list:
        if idx not in cache:
            txt = source_texts_in_order[idx]
            chunks = [txt[i:i + 600] for i in range(0, min(len(txt), 6000), 600)] or ([txt] if txt else [])
            cache[idx] = embed_passages(chunks) if chunks else []
        return cache[idx]

    total = unsupported = corroborated = 0
    flagged: list[str] = []
    single_source: list[str] = []
    for s in target:
        total += 1
        is_insufficient = "insufficient evidence" in s.lower()
        nums = [int(n) for n in re.findall(r"\[(\d+)\]", s)]
        cited_idxs = [n - 1 for n in nums if 0 <= n - 1 < nsrc]
        if not cited_idxs:
            # uncited claim or out-of-range [n]: unsupported by default (never match against "any" source).
            if not is_insufficient:
                unsupported += 1
                flagged.append(s)
            continue
        cvec = embed_query(s)

        def _supports(idx: int) -> bool:
            return any(cosine(cvec, v) >= threshold for v in _emb(idx))

        if not any(_supports(i) for i in cited_idxs):
            if not is_insufficient:
                unsupported += 1
                flagged.append(s)
            continue
        # cross-source corroboration: is the claim ALSO supported by a source OTHER than the one it cites?
        others = sum(1 for j in range(nsrc) if j not in cited_idxs and _supports(j))
        if others >= 1:
            corroborated += 1
        elif not is_insufficient:
            single_source.append(s)
    risk = round(unsupported / total, 3) if total else 0.0
    consensus = round(corroborated / total, 3) if total else 0.0
    return {"risk": risk, "total": total, "unsupported": unsupported, "flagged": flagged,
            "single_source": single_source, "consensus": consensus}
