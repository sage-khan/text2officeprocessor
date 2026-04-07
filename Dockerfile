# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools only in the builder stage
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libxml2-dev \
        libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY src/ ./src/

RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt \
    && pip install --prefix=/install --no-cache-dir -e . --no-deps


# ── Stage 2: minimal runtime image ───────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Muhammad Danyal (Sage) Khan"
LABEL description="MD2Office — convert markdown/text/HTML to PPTX, DOCX, XLSX"
LABEL version="0.1.0"

# LibreOffice is needed only for the optional PDF verification step.
# Install it here if you need visual verification inside the container;
# otherwise comment it out to keep the image lean (~200MB vs ~1.5GB).
# RUN apt-get update && apt-get install -y --no-install-recommends libreoffice \
#     && rm -rf /var/lib/apt/lists/*

# Runtime dependencies for lxml (used by python-pptx)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 \
        libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
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

ENTRYPOINT ["python", "-m", "src.cli.main"]
CMD ["--help"]
