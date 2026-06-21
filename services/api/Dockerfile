FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY . .
ENV PORT=7000
EXPOSE 7000
# apply all migrations (idempotent, IF NOT EXISTS) before serving, so a fresh/updated DB is always
# in sync — no missed migrations, no manual step.
CMD ["sh", "-c", "python -m athena.migrate && uvicorn athena.api.app:app --host 0.0.0.0 --port ${PORT}"]
