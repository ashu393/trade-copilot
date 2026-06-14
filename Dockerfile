# Trade Intelligence Copilot — container image for the FastAPI service.
# Build:  docker build -t trade-copilot .
# Run:    docker run -p 8000:8000 --env-file .env trade-copilot
#         then POST http://localhost:8000/ask {"question": "..."}
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e .

# Application data and the rest of the code.
COPY data ./data
COPY partc ./partc

# Build the DuckDB file at image build time so the first request is fast.
RUN python -c "from copilot.db import Database; Database().build()"

EXPOSE 8000

# ANTHROPIC_API_KEY is supplied at run time via --env-file/.env (never baked in).
# JSON/exec form (clean signal handling for graceful stop/restart) while still
# expanding $PORT (injected by Railway/Render/etc.); `exec` makes uvicorn PID 1
# so it receives SIGTERM directly. Defaults to 8000 locally.
CMD ["sh", "-c", "exec uvicorn copilot.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
