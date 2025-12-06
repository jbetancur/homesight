"""
Server-Sent Events (SSE) Service for real-time incident notifications
"""

import asyncio
import logging
from typing import Set
from fastapi import Request
from sse_starlette.sse import EventSourceResponse
import json

logger = logging.getLogger(__name__)


class SSEService:
    """
    Manages SSE connections and broadcasts incident alerts to connected clients.
    """
    
    def __init__(self):
        self.clients: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        logger.info("✅ SSE Service initialized")
    
    async def subscribe(self, request: Request) -> EventSourceResponse:
        """
        Creates an SSE connection for a client.
        Returns an EventSourceResponse that streams events.
        """
        queue = asyncio.Queue(maxsize=10)
        
        async with self._lock:
            self.clients.add(queue)
        
        logger.info(f"📡 New SSE client connected (total: {len(self.clients)})")
        
        async def event_generator():
            try:
                # Send initial connection confirmation
                yield {
                    "event": "connected",
                    "data": json.dumps({"message": "Connected to HomeSight incident stream"})
                }
                
                # Stream events from queue
                while True:
                    if await request.is_disconnected():
                        break
                    
                    try:
                        # Wait for event with timeout to check disconnection
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield event
                    except asyncio.TimeoutError:
                        # Send keepalive comment every 30s
                        yield {"event": "ping", "data": "keepalive"}
            except asyncio.CancelledError:
                logger.info("📡 SSE client connection cancelled")
            finally:
                async with self._lock:
                    self.clients.discard(queue)
                logger.info(f"📡 SSE client disconnected (remaining: {len(self.clients)})")
        
        return EventSourceResponse(event_generator())
    
    async def broadcast_incident(self, incident: dict):
        """
        Broadcasts an incident alert to all connected SSE clients.
        
        Args:
            incident: Incident data from backend
        """
        if not self.clients:
            logger.info(f"📡 No SSE clients connected (incident: {incident.get('id')}, skipping broadcast)")
            return
        
        logger.info(f"📡 Broadcasting incident {incident.get('id')} to {len(self.clients)} clients")
        
        # Create friendly notification message
        severity = incident.get("severity", "info").upper()
        title = incident.get("title", "New Incident")
        zone = incident.get("zone_id", "unknown location")
        
        # Severity emoji mapping
        emoji_map = {
            "CRITICAL": "🚨",
            "WARNING": "⚠️",
            "INFO": "ℹ️"
        }
        emoji = emoji_map.get(severity, "📢")
        
        message = f"{emoji} {severity}: {title}"
        if zone and zone != "unknown location":
            message += f" in {zone}"
        
        event_data = {
            "type": "incident_alert",
            "incident": {
                "id": incident.get("id"),
                "title": incident.get("title"),
                "description": incident.get("description"),
                "severity": incident.get("severity"),
                "zone_id": incident.get("zone_id"),
                "device_id": incident.get("device_id"),
                "created_at": incident.get("created_at"),
                "status": incident.get("status"),
            },
            "message": message,
            "timestamp": incident.get("created_at")
        }
        
        event = {
            "event": "incident_alert",
            "data": json.dumps(event_data)
        }
        
        # Broadcast to all clients
        disconnected_clients = []
        async with self._lock:
            for queue in self.clients:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("SSE client queue full, dropping event")
                    disconnected_clients.append(queue)
        
        # Clean up disconnected clients
        if disconnected_clients:
            async with self._lock:
                for queue in disconnected_clients:
                    self.clients.discard(queue)
        
        logger.info(f"📡 Broadcasted incident alert to {len(self.clients)} clients: {message}")


# Global SSE service instance
_sse_service = None


def get_sse_service() -> SSEService:
    """Get or create the global SSE service instance"""
    global _sse_service
    if _sse_service is None:
        _sse_service = SSEService()
    return _sse_service
