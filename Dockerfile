FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-driver curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY main.py healthcheck.py ./
COPY config ./config
COPY prompts ./prompts

RUN useradd --create-home --uid 10001 app && \
    mkdir -p /data /browser-profile /app/var/screenshots && \
    chown -R app:app /data /browser-profile /app

USER app

ENV BRAVE_PATH=/usr/bin/chromium \
    BOT_PROFILE=/browser-profile \
    SQLITE_PATH=/data/abie_gpt.db \
    DATABASE_URL=sqlite:////data/abie_gpt.db

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "healthcheck.py"]

CMD ["python", "main.py"]
