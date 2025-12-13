FROM python:3.11-slim

WORKDIR /app

# ------------------------------------------------------------
# Install system dependencies (including OCR + PDF libs + Vulkan for GPU)
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    curl \
    git \
    ca-certificates \
    # Build tools for compiling from source
    autoconf \
    automake \
    libtool \
    pkg-config \
    # OCR and PDF processing
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
    # Vulkan support for AMD GPU acceleration (Radeon 780M / RDNA3)
    mesa-vulkan-drivers \
    libvulkan1 \
    libvulkan-dev \
    vulkan-tools \
    glslang-tools \
    glslc \
    spirv-tools \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# Copy requirements + install Python deps
# ------------------------------------------------------------
COPY ai-sidecar/requirements.txt .

# Install non-GPU dependencies first (faster layer caching)
RUN grep -v "llama-cpp-python" requirements.txt > requirements-base.txt && \
    pip install --no-cache-dir -r requirements-base.txt

# Build llama-cpp-python with Vulkan backend for AMD GPU acceleration
# This compiles llama.cpp with Vulkan support for RADV (AMD open-source driver)
ENV CMAKE_ARGS="-DGGML_VULKAN=ON"
RUN pip install --no-cache-dir llama-cpp-python==0.3.16 --force-reinstall --no-binary :all:

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
# Start the app with Gunicorn + Uvicorn workers
# Optimized for Vulkan GPU (AMD Radeon 780M) workloads:
# - 2 workers: Balance between concurrency and GPU memory
# - 1 thread per worker: GPU operations are synchronous
# - 120s timeout: Allow time for LLM inference on GPU
# - preload: Share model weights across workers (saves GPU memory)
# See gunicorn.conf.py for full configuration
# ------------------------------------------------------------
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
