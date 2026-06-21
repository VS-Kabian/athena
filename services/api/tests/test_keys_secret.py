import pytest
from unittest.mock import patch, AsyncMock
from cryptography.fernet import Fernet
import athena.api.keys as keys


@pytest.mark.asyncio
async def test_uses_env_secret_for_roundtrip():
    secret = Fernet.generate_key().decode()
    with patch("athena.api.keys.settings.athena_secret", secret):
        enc = keys._fernet().encrypt(b"sk-live-123").decode()
        with patch("athena.api.keys.fetch", AsyncMock(return_value=[{"key_enc": enc}])):
            assert await keys.get_key("groq") == "sk-live-123"


@pytest.mark.asyncio
async def test_undecryptable_row_treated_as_unset():
    secret = Fernet.generate_key().decode()
    with patch("athena.api.keys.settings.athena_secret", secret), \
         patch("athena.api.keys.fetch", AsyncMock(return_value=[{"key_enc": "garbage-not-fernet"}])):
        assert await keys.get_key("groq") is None


@pytest.mark.asyncio
async def test_list_keys_skips_undecryptable_rows():
    secret = Fernet.generate_key().decode()
    with patch("athena.api.keys.settings.athena_secret", secret):
        good = keys._fernet().encrypt(b"sk-good").decode()
        rows = [{"provider": "groq", "key_enc": good}, {"provider": "gemini", "key_enc": "broken"}]
        with patch("athena.api.keys.fetch", AsyncMock(return_value=rows)):
            out = await keys.list_keys()
    assert [k["provider"] for k in out] == ["groq"]  # broken row skipped, not fatal
