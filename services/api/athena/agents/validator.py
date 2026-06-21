from urllib.parse import urlparse

# Tier A — authoritative: gov/edu/intl TLDs + major academic / standards bodies + peer-review venues
TIER_A_TLDS = (".gov", ".edu", ".int", ".ac.uk", ".edu.au", ".gov.uk")
TIER_A_DOMAINS = ("arxiv.org", "nature.com", "science.org", "acm.org", "ieee.org",
                  "springer.com", "sciencedirect.com", "semanticscholar.org", "doi.org",
                  "nih.gov", "who.int", "ncbi.nlm.nih.gov", "jstor.org", "nasa.gov",
                  "europa.eu", "oecd.org", "worldbank.org",
                  # peer-review / academic venues
                  "openreview.net", "aclanthology.org", "neurips.cc", "proceedings.mlr.press",
                  "paperswithcode.com", "pnas.org", "biorxiv.org", "medrxiv.org", "dl.acm.org")
# Tier B — official docs / code / standards + recognized framework & vendor primary sources
TIER_B_DOMAINS = ("github.com", "gitlab.com", "python.org", "pytorch.org", "tensorflow.org",
                  "kubernetes.io", "mozilla.org", "developer.mozilla.org", "w3.org",
                  "ietf.org", "rfc-editor.org", "wikipedia.org", "huggingface.co",
                  # framework / vendor official sites & docs (the primary source for their own product)
                  "langchain.com", "crewai.com", "llamaindex.ai", "modelcontextprotocol.io",
                  "learn.microsoft.com", "platform.openai.com", "openai.com", "anthropic.com",
                  "ai.google.dev", "developers.google.com", "readthedocs.io",
                  "langchain-ai.github.io", "microsoft.github.io",
                  # cloud-provider docs + more vendor/framework primary sources & official blogs
                  "docs.github.com", "aws.amazon.com", "cloud.google.com", "azure.microsoft.com",
                  "blog.langchain.dev", "langchain.dev", "docs.langchain.com", "ag2.ai",
                  "microsoft.com", "googleblog.com", "developer.nvidia.com", "fastapi.tiangolo.com",
                  "vercel.com", "docs.docker.com", "cloudflare.com", "redis.io", "postgresql.org")
# Tier C — reputable press / established engineering publications
TIER_C_DOMAINS = ("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
                  "wsj.com", "economist.com", "ft.com", "theguardian.com", "arstechnica.com",
                  "wired.com", "theverge.com", "techcrunch.com",
                  "venturebeat.com", "infoworld.com", "thenewstack.io", "infoq.com", "zdnet.com")
SOCIAL = ("instagram.", "facebook.", "pinterest.", "tiktok.", "x.com", "twitter.",
          "quora.com", "reddit.com")
JUNK = ("hire ", "hire-", "/hire", "/jobs", "careers", "buy now", "for sale",
        "coupon", "discount code", "best vpn", "top 10 ")


def _registered_match(host: str, domains) -> bool:
    """Match the registered domain, not any substring — so 'github.com.phishing.io' does NOT
    score as github.com. Matches host == d or host ending in '.' + d."""
    return any(host == d or host.endswith("." + d) for d in domains)


def score_source(url: str, title: str = "") -> float:
    u = (url or "").lower()
    p = urlparse(u)
    host = (p.hostname or "").lower()
    path = (p.path or "").lower()
    blob = host + " " + (title or "").lower()
    score = 0.35
    if u.startswith("https://"):
        score += 0.08
    if any(host.endswith(t) for t in TIER_A_TLDS) or _registered_match(host, TIER_A_DOMAINS):
        score += 0.42
    elif _registered_match(host, TIER_B_DOMAINS) or host.startswith("docs.") or "/docs" in path:
        score += 0.30
    elif _registered_match(host, TIER_C_DOMAINS):
        score += 0.20
    if any(s in host for s in SOCIAL):
        score -= 0.40
    if any(j in blob for j in JUNK):
        score -= 0.35
    return max(0.0, min(round(score, 3), 1.0))


def is_validated(url: str, title: str = "", threshold: float = 0.6) -> bool:
    return score_source(url, title) >= threshold
