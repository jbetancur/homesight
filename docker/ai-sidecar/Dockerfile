FROM python:3.11-slim

WORKDIR /app

# ------------------------------------------------------------
# Install system dependencies (including OCR + PDF libs)
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ca-certificates \
    tesseract-ocr \
    libtesseract-dev \
    libleptonica-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libwebp-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Copy requirements + install Python deps
# ------------------------------------------------------------
COPY ai-sidecar/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ------------------------------------------------------------
# Pre-download FastEmbed model
# ------------------------------------------------------------
ENV FASTEMBED_CACHE_PATH=/app/models/fastembed
RUN mkdir -p $FASTEMBED_CACHE_PATH && \
    python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='$FASTEMBED_CACHE_PATH')" || true

# ------------------------------------------------------------
# Copy application
# ------------------------------------------------------------
COPY ai-sidecar /app

# ------------------------------------------------------------
# Create required runtime directories
# ------------------------------------------------------------
RUN mkdir -p /var/lib/homesight/rag /root/homesight/manuals

# ------------------------------------------------------------
# Expose API
# ------------------------------------------------------------
EXPOSE 8001

# ------------------------------------------------------------
# Healthcheck endpoint
# ------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# ------------------------------------------------------------
# Start the app
# ------------------------------------------------------------
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
