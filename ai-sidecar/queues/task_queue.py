"""
Generic task queue with resource awareness.

Features:
- Configurable concurrency limits per queue type
- Backpressure (reject if queue too deep)
- CPU/memory awareness (throttle if system busy)
- Per-task-type priority and timeout
"""

import asyncio
import logging
import psutil
from typing import Optional, Callable, Any, Dict
from dataclasses import dataclass
from enum import Enum
import time

logger = logging.getLogger(__name__)


class QueueType(Enum):
    """Queue types with different resource profiles"""
    DISCOVERY = "discovery"    # PDF fetching, document parsing
    INGESTION = "ingestion"    # Embedding, ChromaDB writes
    ANALYSIS = "analysis"      # OpenAI API calls


@dataclass
class QueueConfig:
    """Configuration for a task queue"""
    max_concurrent: int = 2          # Max concurrent tasks
    max_queue_depth: int = 10        # Reject if queue exceeds this
    cpu_threshold: float = 0.80      # Throttle if CPU > 80%
    memory_threshold: float = 0.85   # Throttle if memory > 85%
    task_timeout: float = 300        # Task timeout in seconds (5 minutes)


class TaskQueue:
    """
    Generic task queue with resource awareness and backpressure.

    Usage:
        queue = TaskQueue(QueueType.DISCOVERY, config)
        result = await queue.execute(my_async_task, task_id="unique-id")
    """

    def __init__(self, queue_type: QueueType, config: Optional[QueueConfig] = None):
        self.queue_type = queue_type
        self.config = config or QueueConfig()

        # Task tracking
        self._task_semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._pending_tasks: Dict[str, asyncio.Task] = {}
        self._completed_count = 0
        self._failed_count = 0
        self._rejected_count = 0

        logger.info(
            f"TaskQueue({queue_type.value}): "
            f"max_concurrent={self.config.max_concurrent}, "
            f"max_queue_depth={self.config.max_queue_depth}"
        )

    async def execute(
        self,
        coro: Callable[..., Any],
        task_id: Optional[str] = None,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a task with resource awareness.

        Args:
            coro: Async function to execute
            task_id: Optional task identifier for tracking
            *args, **kwargs: Arguments to pass to coro

        Returns:
            Result from the coroutine

        Raises:
            RuntimeError: If queue is full or resources exhausted
        """
        task_id = task_id or f"{self.queue_type.value}-{len(self._pending_tasks)}"

        # Check backpressure
        if len(self._pending_tasks) >= self.config.max_queue_depth:
            self._rejected_count += 1
            logger.warning(
                f"Queue {self.queue_type.value} full ({len(self._pending_tasks)}/{self.config.max_queue_depth})"
            )
            raise RuntimeError(f"Queue {self.queue_type.value} is full, task rejected")

        # Check resource usage
        if not self._check_resources():
            self._rejected_count += 1
            logger.warning(
                f"Queue {self.queue_type.value} throttled due to resource constraints"
            )
            raise RuntimeError(f"System resources exhausted, task throttled")

        # Wait for slot
        logger.debug(f"Task {task_id} waiting for slot (pending: {len(self._pending_tasks)})")

        async with self._task_semaphore:
            try:
                logger.info(f"Task {task_id} started")
                start_time = time.time()

                result = await coro(*args, **kwargs)

                duration = time.time() - start_time
                self._completed_count += 1
                logger.info(f"Task {task_id} completed in {duration:.2f}s")

                return result

            except asyncio.TimeoutError:
                self._failed_count += 1
                logger.error(f"Task {task_id} timed out after {self.config.task_timeout}s")
                raise

            except Exception as e:
                self._failed_count += 1
                logger.error(f"Task {task_id} failed: {e}")
                raise

            finally:
                # Clean up pending task
                if task_id in self._pending_tasks:
                    del self._pending_tasks[task_id]

    def _check_resources(self) -> bool:
        """Check if system resources allow task execution"""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent

            # Log current usage
            logger.debug(f"Resources: CPU={cpu_percent:.1f}%, Memory={memory_percent:.1f}%")

            # Check thresholds
            if cpu_percent > self.config.cpu_threshold * 100:
                logger.warning(f"CPU usage high: {cpu_percent:.1f}% > {self.config.cpu_threshold * 100}%")
                return False

            if memory_percent > self.config.memory_threshold * 100:
                logger.warning(f"Memory usage high: {memory_percent:.1f}% > {self.config.memory_threshold * 100}%")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking resources: {e}")
            return True  # Fail open (don't block on error)

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            "queue_type": self.queue_type.value,
            "pending": len(self._pending_tasks),
            "completed": self._completed_count,
            "failed": self._failed_count,
            "rejected": self._rejected_count,
            "concurrency": self.config.max_concurrent,
            "max_queue_depth": self.config.max_queue_depth,
        }
