import asyncio
import re

from litellm import acompletion
from .registry import litellm_model


def redact_keys(text: str) -> str:
    """Scrub standard API key/token patterns and high-entropy secret-like strings
    from text to prevent secret leakage in errors/logs."""
    if not text:
        return text
    # Google API keys: AIzaSy...
    text = re.sub(r"\bAIza[a-zA-Z0-9_-]{16,}\b", "[REDACTED]", text)
    # Other standard key prefixes (e.g. sk-..., gsk-..., tvly-... for Tavily, serper, slack tokens)
    text = re.sub(r"\b(?:sk|gsk|tvly|serper|xoxb|xoxp|xapp|xoxs)-[a-zA-Z0-9_-]{12,}\b", "[REDACTED]", text)
    # Generic high-entropy alphanumeric keys/hashes (30+ characters)
    text = re.sub(r"\b[a-zA-Z0-9]{30,}\b", "[REDACTED]", text)
    return text

# errors where retrying is pointless (bad credentials / bad request) — fail fast on these
_NON_RETRYABLE = ("invalid api key", "invalid_api_key", "401", "unauthorized", "permission",
                  "authentication", "context window", "context_length")


def _retryable(e: Exception) -> bool:
    low = str(e).lower()
    return not any(s in low for s in _NON_RETRYABLE)


async def complete(provider: str, model: str, messages: list[dict], api_key: str | None,
                   timeout: float = 60, _attempts: int = 3, **kw) -> str:
    # retry transient failures (rate limits, 5xx, network blips) with exponential backoff; never
    # retry auth/bad-request errors.
    n = max(1, _attempts)
    delay = 1.0
    for attempt in range(n):
        try:
            resp = await acompletion(
                model=litellm_model(provider, model),
                messages=messages,
                api_key=api_key,
                timeout=timeout,
                **kw,
            )
            choices = getattr(resp, "choices", None) or []
            if not choices:
                return ""   # provider returned no choices -> empty string, never an IndexError
            return choices[0].message.content or ""   # never None (tool-use/refusal -> "")
        except Exception as e:
            if attempt == n - 1 or not _retryable(e):
                raise
            await asyncio.sleep(delay)
            delay *= 2
    return ""   # unreachable (loop always returns or raises) — defensive for the -> str contract


async def stream_complete(provider: str, model: str, messages: list[dict], api_key: str | None,
                          timeout: float = 60, on_delta=None, on_reasoning=None, **kw) -> tuple[str, dict]:
    """Stream a completion: invokes ``on_delta(text)`` per content chunk and ``on_reasoning(text)``
    per reasoning chunk (DeepSeek-R1 etc.), returning the full text + a usage dict
    ({prompt_tokens, completion_tokens, total_tokens, cost}). Raises like ``complete`` so the
    caller's shrink/retry logic still applies."""
    full, usage, finish_reason = [], {}, None
    lm = litellm_model(provider, model)
    resp = await acompletion(model=lm, messages=messages, api_key=api_key, timeout=timeout,
                             stream=True, stream_options={"include_usage": True}, **kw)
    async for chunk in resp:
        try:
            choices = getattr(chunk, "choices", None)
            if choices:
                fr = getattr(choices[0], "finish_reason", None)
                if fr:
                    finish_reason = fr   # "length" => the model was cut off at max_tokens (truncated)
                delta = getattr(choices[0], "delta", None)
                txt = getattr(delta, "content", None) if delta else None
                if txt:
                    full.append(txt)
                    if on_delta:
                        await on_delta(txt)
                rc = getattr(delta, "reasoning_content", None) if delta else None
                if rc and on_reasoning:
                    await on_reasoning(rc)
            u = getattr(chunk, "usage", None)
            if u:
                usage = {"prompt_tokens": getattr(u, "prompt_tokens", None),
                         "completion_tokens": getattr(u, "completion_tokens", None),
                         "total_tokens": getattr(u, "total_tokens", None)}
        except Exception:
            continue
    text = "".join(full)
    if finish_reason:
        usage["finish_reason"] = finish_reason
    try:
        from litellm import cost_per_token
        pc, cc = cost_per_token(model=lm, prompt_tokens=usage.get("prompt_tokens") or 0,
                                completion_tokens=usage.get("completion_tokens") or 0)
        usage["cost"] = round((pc or 0.0) + (cc or 0.0), 6)
    except Exception:
        pass
    return text, usage
