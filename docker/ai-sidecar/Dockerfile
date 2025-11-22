FROM python:3.11-slim

# Install system deps for PDF conversion and headless Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    build-essential \
    cmake \
    git \
    pkg-config \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libgomp1 \
    fonts-liberation \
    libnss3 \
    libx11-6 \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    chromium \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python deps
COPY ai-sidecar/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy sidecar source
COPY ai-sidecar/ /app/

EXPOSE 8001

# Start app with uvicorn
# Uvicorn will use multiple workers to handle concurrent requests
# Queue remaining requests - the ThreadPoolExecutor will queue analyze jobs
ENTRYPOINT ["sh", "-c"]
CMD ["uvicorn main:app --host 0.0.0.0 --port 8001 --workers=2 --timeout-keep-alive 300 --loop asyncio"]
