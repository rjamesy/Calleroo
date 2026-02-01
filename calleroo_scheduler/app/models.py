"""
Pydantic models for the Scheduler Service API.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskMode(str, Enum):
    """Execution mode for a scheduled task."""
    DIRECT = "DIRECT"
    BRIEF_START = "BRIEF_START"


class TaskStatus(str, Enum):
    """Status of a scheduled task."""
    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


# =============================================================================
# Request Models
# =============================================================================


class CreateTaskRequest(BaseModel):
    """Request body for creating a scheduled task."""

    runAtUtc: str = Field(
        ...,
        description="ISO 8601 UTC timestamp when the task should run",
        json_schema_extra={"example": "2026-02-01T22:00:00Z"}
    )
    backendBaseUrl: str = Field(
        ...,
        description="Base URL of the backend API",
        json_schema_extra={"example": "https://api.callerooapp.com"}
    )
    agentType: str = Field(
        ...,
        description="Type of agent to use",
        json_schema_extra={"example": "STOCK_CHECKER"}
    )
    conversationId: str = Field(
        ...,
        description="Conversation ID to associate with the call",
        json_schema_extra={"example": "conv-123-abc"}
    )
    mode: TaskMode = Field(
        ...,
        description="Execution mode: DIRECT (use stored scriptPreview) or BRIEF_START (call /brief first)"
    )
    payload: Dict[str, Any] = Field(
        ...,
        description="Mode-specific payload data"
    )
    timezone: Optional[str] = Field(
        None,
        description="Original timezone (for reference)",
        json_schema_extra={"example": "Australia/Brisbane"}
    )
    notifyTarget: Optional[str] = Field(
        None,
        description="Target for notifications (stub for future use)",
        json_schema_extra={"example": "user-123"}
    )
    backendAuthToken: Optional[str] = Field(
        None,
        description="Optional auth token for backend calls"
    )


class CancelTaskRequest(BaseModel):
    """Request body for canceling a task (currently empty, may add reason later)."""
    pass


# =============================================================================
# Response Models
# =============================================================================


class CreateTaskResponse(BaseModel):
    """Response after creating a scheduled task."""
    taskId: str
    status: str


class TaskEventResponse(BaseModel):
    """A single task event in the log."""
    id: int
    tsUtc: str
    level: str
    message: str


class TaskResponse(BaseModel):
    """Full task details response."""
    taskId: str
    status: str
    runAtUtc: str
    agentType: str
    conversationId: str
    mode: str
    placeId: Optional[str] = None
    phoneE164: Optional[str] = None
    callId: Optional[str] = None
    lastError: Optional[str] = None
    createdAt: str
    updatedAt: str
    events: List[TaskEventResponse] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    """Response for listing tasks."""
    tasks: List[TaskResponse]
    total: int


class CancelTaskResponse(BaseModel):
    """Response after canceling a task."""
    taskId: str
    status: str
    message: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str


# =============================================================================
# Backend API Models (what we send to backend_v2)
# =============================================================================


class BackendCallBriefPlace(BaseModel):
    """Place data for /call/brief request."""
    placeId: str
    businessName: str
    formattedAddress: Optional[str] = None
    phoneE164: str


class BackendCallBriefDisclosure(BaseModel):
    """Disclosure settings for /call/brief request."""
    nameShare: bool = False
    phoneShare: bool = False


class BackendCallBriefFallbacks(BaseModel):
    """Fallback settings for /call/brief request."""
    askETA: Optional[bool] = None
    askNearestStore: Optional[bool] = None
    retryIfNoAnswer: Optional[bool] = None
    retryIfBusy: Optional[bool] = None
    leaveVoicemail: Optional[bool] = None


class BackendCallBriefRequest(BaseModel):
    """Request body for backend /call/brief endpoint."""
    conversationId: str
    agentType: str
    place: BackendCallBriefPlace
    slots: Dict[str, Any] = Field(default_factory=dict)
    disclosure: BackendCallBriefDisclosure = Field(default_factory=BackendCallBriefDisclosure)
    fallbacks: BackendCallBriefFallbacks = Field(default_factory=BackendCallBriefFallbacks)


class BackendCallStartRequest(BaseModel):
    """Request body for backend /call/start endpoint."""
    conversationId: str
    agentType: str
    placeId: str
    phoneE164: str
    scriptPreview: str
    slots: Dict[str, Any] = Field(default_factory=dict)


class BackendCallBriefResponse(BaseModel):
    """Response from backend /call/brief endpoint."""
    objective: str
    scriptPreview: str
    confirmationChecklist: List[str]
    normalizedPhoneE164: str
    requiredFieldsMissing: List[str]
    aiCallMade: bool
    aiModel: str


class BackendCallStartResponse(BaseModel):
    """Response from backend /call/start endpoint."""
    callId: str
    status: str
    message: str
