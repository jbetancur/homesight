FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ai-sidecar/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download FastEmbed model to avoid runtime network calls
# This prevents rate limiting and CPU spikes on container startup
ENV FASTEMBED_CACHE_PATH=/app/models/fastembed
RUN mkdir -p $FASTEMBED_CACHE_PATH && \
    python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='$FASTEMBED_CACHE_PATH')" || true

# Copy AI sidecar code
COPY ai-sidecar /app

# Create necessary directories
RUN mkdir -p /var/lib/homesight/rag /root/.homesight/manuals

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
