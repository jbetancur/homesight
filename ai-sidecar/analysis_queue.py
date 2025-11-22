"""Request queue manager for AI analysis tasks"""

import asyncio
import logging
from typing import Callable, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QueuedRequest:
    """Represents a queued analysis request"""
    id: str
    task: Callable
    priority: int = 0


class AnalysisQueue:
    """
    Queue for managing concurrent analysis requests.
    Limits concurrent execution while queuing remaining requests.
    """

    def __init__(self, max_concurrent: int = 4):
        """
        Initialize queue with max concurrent executions.

        Args:
            max_concurrent: Maximum number of concurrent analysis tasks
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_count = 0
        self.queued_count = 0

    async def execute(self, task: Callable, task_id: str = "unknown") -> Any:
        """
        Execute a task with queuing.

        If max concurrent limit is reached, task is queued and waits.

        Args:
            task: Async callable to execute
            task_id: Optional ID for logging

        Returns:
            Result from task execution
        """
        async with self.semaphore:
            self.active_count += 1
            if self.queued_count > 0:
                logger.info(f"Task {task_id} started (queue depth: {self.queued_count})")

            try:
                return await task()
            finally:
                self.active_count -= 1

    def queue_request(self) -> None:
        """Track a queued request"""
        self.queued_count += 1

    def dequeue_request(self) -> None:
        """Track dequeued request"""
        if self.queued_count > 0:
            self.queued_count -= 1

    def get_stats(self) -> dict:
        """Get queue statistics"""
        return {
            "active": self.active_count,
            "queued": self.queued_count,
            "max_concurrent": self.max_concurrent,
            "utilization": self.active_count / self.max_concurrent
        }
