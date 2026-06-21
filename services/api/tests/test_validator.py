from athena.agents.validator import score_source, is_validated


def test_official_framework_and_academic_domains_now_validate():
    # recognized primary sources for AI/agent topics should validate...
    assert is_validated("https://www.langchain.com/resources/ai-agent-frameworks", "LangChain")
    assert is_validated("https://openreview.net/forum?id=abc123", "Agent Eval Survey")
    assert is_validated("https://learn.microsoft.com/en-us/agent-framework", "Microsoft Agent Framework")
    assert is_validated("https://platform.openai.com/docs/guides/agents", "OpenAI Agents SDK")
    # ...but a generic marketing blog still does NOT
    assert not is_validated("https://uvik.net/blog/agentic-ai-frameworks", "Agentic AI Frameworks")


def test_spam_not_validated():
    assert not is_validated("https://example.com/hire-php-developers", "Hire PHP Developers - Laravel Experts")
    assert not is_validated("https://www.instagram.com/p/x", "Instagram")

def test_authoritative_validated():
    assert is_validated("https://arxiv.org/abs/2312.10997", "A Survey of RAG")
    assert is_validated("https://github.com/run-llama/llama_index", "LlamaIndex")

def test_plain_blog_not_validated():
    assert not is_validated("https://medium.com/@x/post", "Some blog post")

def test_trusted_beats_spam():
    assert score_source("https://nih.gov/x") > score_source("https://example.com/hire-php", "Hire PHP")


def test_registered_domain_matching_blocks_spoofing():
    # a look-alike host must NOT inherit github's authority via substring matching
    assert is_validated("https://github.com/run-llama/llama_index", "LlamaIndex")
    assert not is_validated("https://github.com.phishing.io/fake", "Fake repo")
    assert score_source("https://github.com.phishing.io/fake") < score_source("https://github.com/x")


def test_tiered_authority_ordering():
    a = score_source("https://arxiv.org/abs/1", "paper")        # tier A
    b = score_source("https://github.com/x", "repo")            # tier B
    c = score_source("https://reuters.com/article", "news")     # tier C
    plain = score_source("https://randomblog.example/post", "post")
    assert a > b > c > plain


def test_reputable_press_is_validated():
    assert is_validated("https://www.reuters.com/technology/x", "Reuters")
    assert is_validated("https://www.gov.uk/guidance", "UK gov")
