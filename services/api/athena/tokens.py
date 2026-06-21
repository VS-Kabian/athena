"""Lightweight token estimation for proactive prompt budgeting.

We talk to several providers (Groq/Llama, Gemini, DeepSeek) and none share OpenAI's
tokenizer exactly, so an exact count isn't possible without each vendor's tokenizer.
tiktoken's ``cl100k_base`` is a good *generic* approximation for budgeting; when it isn't
installed we fall back to a character/word heuristic. The number is only used to decide
how much evidence to send before the call (proactive truncation), so a close estimate is
enough — and the synthesizer still keeps its shrink-on-error retry as a backstop.
"""

_enc = None
_tried = False


def _encoder():
    global _enc, _tried
    if not _tried:
        _tried = True
        try:
            import tiktoken
            _enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _enc = None
    return _enc


def count_tokens(text: str) -> int:
    """Estimate the token count of ``text``. Never raises; returns 0 for empty input."""
    if not text:
        return 0
    enc = _encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # heuristic: ~4 chars/token, but never fewer than the word count (a token spans <= 1 word on average)
    return max(len(text) // 4, len(text.split()))
