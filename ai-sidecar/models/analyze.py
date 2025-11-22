"""Analysis-related models"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class AnalyzeRequest(BaseModel):
    """Request for incident or metric analysis"""
    type: str = Field(..., description="Analysis type: 'metrics' or 'incident'")
    data: Dict[str, Any] = Field(..., description="Data to analyze")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class AnalyzeResponse(BaseModel):
    """Response from analysis endpoint"""
    analysis: str = Field(..., description="Analysis summary")
    insights: List[str] = Field(default_factory=list, description="Key insights")
    actions: Optional[List[str]] = Field(None, description="Recommended actions")
    metadata: Optional[Dict[str, Any]] = None
