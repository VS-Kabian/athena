from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:athena@localhost:5432/athena"
    redis_url: str = "redis://localhost:6379/0"
    searxng_url: str = "http://localhost:8080"
    # opt-in headless-browser fallback for JS-rendered pages (requires `playwright install chromium`).
    # off by default: it's heavy and widens the fetch SSRF surface to subresource loads.
    js_fetch: bool = Field(False, validation_alias=AliasChoices("ATHENA_JS_FETCH", "JS_FETCH"))
    # opt-in GraphRAG memory: extract entity-relationship triples from validated sources for multi-hop
    # reasoning + richer cross-run recall. Off by default (extra model calls); env ATHENA_GRAPHRAG=1.
    graphrag: bool = Field(False, validation_alias=AliasChoices("ATHENA_GRAPHRAG", "GRAPHRAG"))
    # Fernet secret for the API-key vault. Set in prod (env ATHENA_SECRET) so the key survives
    # redeploys; if unset, a local file key is used (dev only). Must be a valid Fernet key.
    athena_secret: str | None = None
    # max research runs executing at once; extras queue (env ATHENA_MAX_CONCURRENT_RUNS)
    max_concurrent_runs: int = Field(3, validation_alias=AliasChoices("ATHENA_MAX_CONCURRENT_RUNS", "MAX_CONCURRENT_RUNS"))
    # Optional shared-secret bearer token. Unset (default) = open API for localhost dev. Set it
    # (env ATHENA_API_TOKEN) to require `Authorization: Bearer <token>` on every sensitive endpoint
    # before exposing the API off localhost.
    athena_api_token: str | None = None
    # Comma-separated allowed CORS origins (env ATHENA_CORS_ORIGINS). Never set to "*" in prod.
    cors_origins: str = Field("http://localhost:3000", validation_alias=AliasChoices("ATHENA_CORS_ORIGINS", "CORS_ORIGINS"))
    # Deployment environment (env ATHENA_ENV). When not "dev", a missing ATHENA_SECRET is fatal at
    # startup instead of silently falling back to an ephemeral local key file.
    athena_env: str = "dev"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
