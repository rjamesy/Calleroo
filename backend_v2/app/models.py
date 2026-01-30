"""
Pydantic models for the Conversation API.
Python 3.9 compatible - uses typing.List, typing.Dict, typing.Optional
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    STOCK_CHECKER = "STOCK_CHECKER"
    RESTAURANT_RESERVATION = "RESTAURANT_RESERVATION"


class NextAction(str, Enum):
    ASK_QUESTION = "ASK_QUESTION"
    CONFIRM = "CONFIRM"
    COMPLETE = "COMPLETE"
    FIND_PLACE = "FIND_PLACE"


class InputType(str, Enum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    DATE = "DATE"
    TIME = "TIME"
    BOOLEAN = "BOOLEAN"
    CHOICE = "CHOICE"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class Choice(BaseModel):
    label: str
    value: str


class Question(BaseModel):
    text: str
    field: str
    inputType: InputType
    choices: Optional[List[Choice]] = None
    optional: bool = False


class ConfirmationCard(BaseModel):
    title: str
    lines: List[str]
    confirmLabel: str = "Yes"
    rejectLabel: str = "Not quite"


class ConversationRequest(BaseModel):
    conversationId: str
    agentType: AgentType
    userMessage: str
    slots: Dict[str, Any] = Field(default_factory=dict)
    messageHistory: List[ChatMessage] = Field(default_factory=list)
    debug: bool = False


class PlaceSearchParams(BaseModel):
    """Parameters for place search, returned with FIND_PLACE action."""
    query: str
    area: str
    country: str = "AU"


class ConversationResponse(BaseModel):
    assistantMessage: str
    nextAction: NextAction
    question: Optional[Question] = None
    extractedData: Optional[Dict[str, Any]] = None
    confidence: Confidence = Confidence.MEDIUM
    confirmationCard: Optional[ConfirmationCard] = None
    placeSearchParams: Optional[PlaceSearchParams] = None
    aiCallMade: bool
    aiModel: str


# ============================================================
# Place Search Models (Screen 3 - NO OpenAI, deterministic)
# ============================================================

class PlaceSearchRequest(BaseModel):
    """Request to search for places."""
    query: str
    area: str
    country: str = "AU"
    radius_km: int = 25  # 25, 50, or 100 only


class PlaceCandidate(BaseModel):
    """A place candidate from Google Places API."""
    placeId: str
    name: str
    formattedAddress: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None


class PlaceSearchResponse(BaseModel):
    """Response from place search."""
    radiusKm: int
    candidates: List[PlaceCandidate]
    error: Optional[str] = None


class PlaceDetailsRequest(BaseModel):
    """Request for place details."""
    placeId: str
    country: str = "AU"


class PlaceDetailsResponse(BaseModel):
    """Detailed place information with phone number."""
    placeId: str
    name: str
    formattedAddress: Optional[str] = None
    phoneE164: Optional[str] = None  # E.164 format, None if no valid phone
    error: Optional[str] = None  # "NO_PHONE", "PLACE_NOT_FOUND", etc.
