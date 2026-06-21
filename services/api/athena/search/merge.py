import dataclasses

from .base import SearchHit, url_hash


def rrf_merge(result_lists: list[list[SearchHit]], k: int = 60) -> list[SearchHit]:
    table: dict[str, SearchHit] = {}
    for hits in result_lists:
        for hit in hits:
            key = url_hash(hit.url)
            score = 1.0 / (k + hit.rank)
            if key in table:
                table[key].rrf_score += score
                if hit.provider not in table[key].providers:
                    table[key].providers.append(hit.provider)
            else:
                # copy, never mutate the input hits (they're shared with the provider cache) — keeps
                # rrf_merge pure/idempotent and stops cached hits from accumulating stale scores.
                table[key] = dataclasses.replace(hit, rrf_score=score, providers=[hit.provider])
    # primary: rrf_score desc; secondary: url_hash asc — a deterministic tie-break so equal-score
    # hits order stably (independent of provider iteration order), not by dict insertion order.
    return sorted(table.values(), key=lambda h: (-h.rrf_score, url_hash(h.url)))
