# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools (only needed in this stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libxml2-dev \
        libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY src/ ./src/

# Install all declared dependencies (core + web + LLM extras)
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir \
        "fastapi>=0.110.0" \
        "uvicorn[standard]>=0.29.0" \
        "python-multipart>=0.0.9" \
        "httpx>=0.27.0" \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt \
    && pip install --prefix=/install --no-cache-dir -e . --no-deps


# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Muhammad Danyal (Sage) Khan"
LABEL description="MD2Office — convert markdown/text/HTML to PPTX, DOCX, XLSX"
LABEL version="0.2.6"

# LibreOffice is needed only for optional PDF verification.
# Uncomment to enable (~1.5 GB added to image size):
# RUN apt-get update && apt-get install -y --no-install-recommends libreoffice \
#     && rm -rf /var/lib/apt/lists/*

# Runtime shared libs for lxml / python-pptx
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application source
WORKDIR /app
COPY src/       ./src/
COPY config/    ./config/
COPY templates/ ./templates/
COPY pyproject.toml ./

# /data is the mount point for user files (templates, inputs, outputs)
RUN mkdir /data
VOLUME /data

# Non-root user for security
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser /app /data
USER appuser

# Expose web UI port (used when running: md2office serve --host 0.0.0.0)
EXPOSE 8000

# Health check for the web UI endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

ENTRYPOINT ["python", "-m", "src.cli.main"]
CMD ["--help"]
