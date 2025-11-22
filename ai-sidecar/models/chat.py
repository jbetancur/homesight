"""Chat-related models"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """A single message in a conversation"""
    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None


class ChatSession(BaseModel):
    """Conversation session state"""
    session_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    """Request to chat endpoint"""
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for conversation continuity")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (device info, etc)")


class ChatResponse(BaseModel):
    """Response from chat endpoint"""
    response: str = Field(..., description="AI assistant response")
    session_id: str = Field(..., description="Session ID for this conversation")
    actions_taken: Optional[List[Dict[str, Any]]] = Field(None, description="Actions executed during this turn")
    metadata: Optional[Dict[str, Any]] = None
