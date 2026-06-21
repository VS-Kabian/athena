import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, parse_qsl, urlencode


@dataclass
class SearchHit:
    url: str
    title: str
    snippet: str
    rank: int
    provider: str
    rrf_score: float = 0.0
    providers: list[str] = field(default_factory=list)
    relevance: float = 0.0


_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "gclid", "fbclid", "ref", "ref_src", "mc_cid", "mc_eid", "igshid", "spm"}

_PCT = re.compile(r"%[0-9A-Fa-f]{2}")


def _norm_pct(s: str) -> str:
    # normalize percent-encoding case so %2F and %2f canonicalize identically (minor dedup leak)
    return _PCT.sub(lambda m: m.group(0).lower(), s)


def url_hash(url: str) -> str:
    """Canonical dedup key: scheme-insensitive, strips www./m./amp. + trailing slash + AMP suffix
    + tracking query params (utm_*, gclid, …) + normalizes percent-encoding case (%2F == %2f) so the
    same article isn't counted as several sources."""
    try:
        p = urlsplit(url.split("#")[0].strip())
        host = (p.hostname or "").lower()
        for pre in ("www.", "m.", "amp."):
            if host.startswith(pre):
                host = host[len(pre):]
        path = _norm_pct(p.path.rstrip("/").lower()) or "/"
        if path.endswith("/amp"):
            path = path[:-4] or "/"
        q = sorted((k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING)
        query = urlencode(q)
        return f"{host}{path}" + (f"?{query}" if query else "")
    except Exception:
        return url.split("#")[0].rstrip("/").lower()
