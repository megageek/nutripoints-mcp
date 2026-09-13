FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
    && /opt/venv/bin/pip install --no-cache-dir . \
    && /opt/venv/bin/pip uninstall --yes pip setuptools wheel

FROM python:3.11-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:${PATH}"

RUN apt-get update \
    && apt-get dist-upgrade -y \
    && python -m pip uninstall --yes pip setuptools wheel \
    && rm -rf /usr/local/lib/python3.11/ensurepip \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --create-home app

COPY --from=builder /opt/venv /opt/venv

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["nutripoints-mcp"]
