"""
Gunicorn configuration for HomeSight AI Sidecar
Optimized for Vulkan GPU (AMD Radeon 780M) inference workloads
"""

import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8001"
backlog = 8192

# Worker processes
# For GPU workloads: 2-4 workers is optimal to avoid GPU memory contention
# Override with GUNICORN_WORKERS env var if needed
workers = int(os.getenv("GUNICORN_WORKERS", "2"))

# Worker class - use Uvicorn workers for ASGI support
worker_class = "uvicorn.workers.UvicornWorker"

# Threads per worker
# GPU operations are synchronous, so 1 thread per worker is optimal
threads = 1

# Timeouts
# LLM inference can take time, especially on first load
timeout = 180
keepalive = 5
graceful_timeout = 30

# Process naming
proc_name = "homesight-ai-sidecar"

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Server mechanics
# Preload app code before forking workers
# NOTE: Disabled for LLM workloads - preload causes model to load twice (once per worker)
# For GPU models, each worker needs its own model instance anyway
preload_app = False

# Restart workers after this many requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Worker lifecycle hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Gunicorn server...")


def on_reload(server):
    """Called on reload."""
    server.log.info("Reloading Gunicorn server...")


def when_ready(server):
    """Called just after the server is started."""
    server.log.info(f"Gunicorn server ready. Workers: {workers}, Timeout: {timeout}s")


def worker_int(worker):
    """Called when a worker receives a SIGINT or SIGQUIT signal."""
    worker.log.info(f"Worker {worker.pid} received interrupt signal")


def worker_abort(worker):
    """Called when a worker receives a SIGABRT signal."""
    worker.log.error(f"Worker {worker.pid} aborted")


# Performance tuning for GPU workloads
# Limit request queue to prevent GPU memory exhaustion
worker_connections = 100

# Environment variables for GPU optimization
raw_env = [
    # Vulkan device selection (use first GPU)
    "GGML_VULKAN_DEVICE=0",
    "GGML_VULKAN_PERF=1",
    "GGML_VULKAN_HALT_ON_ERROR=0",
    "GGML_VULKAN_FENCE=0",
    "AMD_VULKAN_ICD=RADV",    
    # Vulkan memory settings
    "VK_LOADER_DEBUG=error",  # Reduce Vulkan loader verbosity
]

# Hooks
def post_fork(server, worker):
    """
    Pin each worker to a dedicated CPU core (LLM performance boost).
    Note: UvicornWorker doesn't expose worker_id, so we use worker age as proxy.
    """
    try:
        import psutil
        cpu_count = psutil.cpu_count(logical=False)
        # UvicornWorker doesn't have worker_id, use age (sequential worker index)
        worker_id = getattr(worker, 'age', 0) % cpu_count
        p = psutil.Process(os.getpid())
        p.cpu_affinity([worker_id])
        worker.log.info(f"Worker {worker.pid} pinned to CPU core {worker_id}")
    except Exception as e:
        worker.log.warning(f"CPU pinning failed: {e}")
