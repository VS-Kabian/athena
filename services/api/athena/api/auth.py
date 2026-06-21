"""Optional shared-secret authentication.

If ``settings.athena_api_token`` is unset (the default), the API is open — this keeps the
localhost developer experience friction-free. Set ``ATHENA_API_TOKEN`` before exposing the API
off localhost and every sensitive endpoint then requires ``Authorization: Bearer <token>``.

Note: the SSE stream endpoint is intentionally NOT gated here — browsers' EventSource cannot send
an Authorization header, so that route relies on the unguessable run-id UUID as a capability.
"""
import hmac

from fastapi import Header, HTTPException

from ..config import settings


def require_auth(authorization: str | None = Header(None)) -> None:
    token = settings.athena_api_token
    if not token:
        return  # auth disabled (localhost dev) — no token configured
    expected = f"Bearer {token}"
    # constant-time compare so a wrong token can't be discovered by timing
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Missing or invalid API token.")
