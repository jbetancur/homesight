"""Session management for multi-turn conversations"""

import logging
import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
from models.chat import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


class SessionService:
    """
    Manages conversation sessions for multi-turn chat.

    In-memory storage for now, can be extended to Redis/DB later.
    """

    def __init__(self, session_timeout_minutes: int = 60):
        self._sessions: Dict[str, ChatSession] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)

    def create_session(self, context: Optional[Dict] = None) -> ChatSession:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        session = ChatSession(
            session_id=session_id,
            messages=[],
            context=context or {}
        )
        self._sessions[session_id] = session
        logger.info(f"Created session: {session_id}")
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Get an existing session"""
        session = self._sessions.get(session_id)

        if not session:
            logger.warning(f"Session not found: {session_id}")
            return None

        # Check if session expired
        if datetime.utcnow() - session.updated_at > self.session_timeout:
            logger.info(f"Session expired: {session_id}")
            del self._sessions[session_id]
            return None

        return session

    def get_or_create_session(self, session_id: Optional[str] = None, context: Optional[Dict] = None) -> ChatSession:
        """Get existing session or create new one"""
        if session_id:
            session = self.get_session(session_id)
            if session:
                # Update context if provided
                if context:
                    session.context.update(context)
                return session

        # Create new session
        return self.create_session(context)

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to a session"""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        message = ChatMessage(
            role=role,
            content=content,
            metadata=metadata
        )
        session.messages.append(message)
        session.updated_at = datetime.utcnow()

        logger.debug(f"Added {role} message to session {session_id}")

    def get_messages(self, session_id: str) -> list:
        """Get all messages in a session"""
        session = self.get_session(session_id)
        if not session:
            return []
        return session.messages

    def clear_session(self, session_id: str):
        """Clear a session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Cleared session: {session_id}")

    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.utcnow()
        expired = [
            sid for sid, session in self._sessions.items()
            if now - session.updated_at > self.session_timeout
        ]

        for sid in expired:
            del self._sessions[sid]

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")

    def get_stats(self) -> Dict:
        """Get session statistics"""
        return {
            "total_sessions": len(self._sessions),
            "active_sessions": len([
                s for s in self._sessions.values()
                if datetime.utcnow() - s.updated_at < timedelta(minutes=5)
            ])
        }
