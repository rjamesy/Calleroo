"""
Calleroo Backend v2 - FastAPI Application

This backend is the SOLE authority for conversation flow.
Every request MUST call OpenAI - no caching, no local heuristics.

Python 3.9 compatible.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    ConversationRequest,
    ConversationResponse,
    PlaceSearchRequest,
    PlaceSearchResponse,
    PlaceDetailsRequest,
    PlaceDetailsResponse,
)
from .openai_service import OpenAIService
from .places_service import GooglePlacesService

# Load environment variables from backend_v2/.env
# Try multiple paths to ensure we find .env
env_paths = [
    Path(__file__).parent.parent / ".env",  # backend_v2/.env
    Path.cwd() / ".env",  # current working directory
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        break
else:
    load_dotenv()  # fallback to default behavior

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "false").lower() == "true" else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Service instances (Python 3.9 compatible type hints)
openai_service: Optional[OpenAIService] = None
places_service: Optional[GooglePlacesService] = None


def _mask_key(key: Optional[str]) -> str:
    """Mask API key showing only last 4 chars."""
    if not key:
        return "(not set)"
    if len(key) <= 4:
        return "****"
    return f"****{key[-4:]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize services."""
    global openai_service, places_service

    logger.info("=" * 60)
    logger.info("Initializing Calleroo Backend v2")
    logger.info("=" * 60)

    # Check and log API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    google_key = os.getenv("GOOGLE_PLACES_API_KEY")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    logger.info(f"OPENAI_API_KEY present: {bool(openai_key)} ({_mask_key(openai_key)})")
    logger.info(f"GOOGLE_PLACES_API_KEY present: {bool(google_key)} ({_mask_key(google_key)})")
    logger.info(f"OPENAI_MODEL: {openai_model}")

    # FAIL FAST if OPENAI_API_KEY is missing
    if not openai_key:
        error_msg = (
            "OPENAI_API_KEY is required. "
            "Set it in backend_v2/.env or as an environment variable."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    openai_service = OpenAIService()
    logger.info("OpenAI service initialized successfully")

    # Initialize Places service if API key is present
    if google_key:
        places_service = GooglePlacesService()
        logger.info("Google Places service initialized successfully")
    else:
        logger.warning("Google Places service NOT initialized - GOOGLE_PLACES_API_KEY missing")

    logger.info("=" * 60)

    yield

    # Shutdown
    if places_service:
        await places_service.close()
    logger.info("Shutting down Calleroo Backend v2")


app = FastAPI(
    title="Calleroo Backend v2",
    description="Unified conversation API driven entirely by OpenAI",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "2.0.0"}


@app.post("/conversation/next", response_model=ConversationResponse)
async def conversation_next(request: ConversationRequest) -> ConversationResponse:
    """
    Process the next turn in a conversation.

    CRITICAL: This endpoint ALWAYS calls OpenAI.
    - NO local question logic
    - NO pre-extraction heuristics
    - NO fallback flows

    The backend is the sole authority for:
    - Assistant message text
    - Next action
    - Question (text/field/inputType/choices/optional)
    - Extracted slots

    The Android client MUST NOT decide questions, slots, flow order, or "what to ask next".
    """
    msg_preview = request.userMessage[:50] + "..." if len(request.userMessage) > 50 else request.userMessage
    logger.info(
        f"Conversation turn: id={request.conversationId}, "
        f"agent={request.agentType}, "
        f"message='{msg_preview}'"
    )

    if openai_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    try:
        # ALWAYS call OpenAI - this is non-negotiable
        # NO local heuristics, NO pre-extraction, NO fallbacks
        response = await openai_service.get_next_turn(
            agent_type=request.agentType,
            user_message=request.userMessage,
            slots=request.slots,
            message_history=request.messageHistory,
        )

        # Verify OpenAI was actually called
        if not response.aiCallMade:
            logger.error("CRITICAL: Response indicates aiCallMade=false, this should never happen")
            raise HTTPException(
                status_code=500,
                detail="openai_not_called: Backend must always call OpenAI"
            )

        # Log the response
        logger.info(
            f"Response: action={response.nextAction}, "
            f"aiCallMade={response.aiCallMade}, "
            f"model={response.aiModel}"
        )

        if request.debug:
            logger.debug(f"Full response: {response.model_dump_json()}")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"openai_failed: {str(e)}"
        )


# ============================================================
# Place Search Endpoints (Screen 3 - NO OpenAI, deterministic)
# ============================================================

@app.post("/places/search", response_model=PlaceSearchResponse)
async def places_search(request: PlaceSearchRequest) -> PlaceSearchResponse:
    """
    Search for places matching the query in the specified area.

    This endpoint does NOT call OpenAI - it is deterministic.
    Uses Google Places Text Search API with area geocoding.

    Returns only candidates (does not filter by phone number here).
    Client should call /places/details to get phone number.
    """
    logger.info(
        f"Places search: query='{request.query}', "
        f"area='{request.area}', "
        f"radius={request.radius_km}km"
    )

    if places_service is None:
        raise HTTPException(
            status_code=500,
            detail="places_key_missing: GOOGLE_PLACES_API_KEY not configured"
        )

    try:
        response = await places_service.text_search(
            query=request.query,
            area=request.area,
            country=request.country,
            radius_km=request.radius_km,
        )

        logger.info(
            f"Places search result: {len(response.candidates)} candidates, "
            f"radius={response.radiusKm}km, "
            f"error={response.error}"
        )

        return response

    except Exception as e:
        logger.error(f"Places search error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"places_search_failed: {str(e)}"
        )


@app.post("/places/details", response_model=PlaceDetailsResponse)
async def places_details(request: PlaceDetailsRequest) -> PlaceDetailsResponse:
    """
    Get detailed information about a specific place.

    This endpoint does NOT call OpenAI - it is deterministic.
    Uses Google Places Details API.

    Returns phoneE164 if the place has a valid phone number.
    Returns error="NO_PHONE" if the place has no valid phone.
    """
    logger.info(f"Places details: placeId='{request.placeId}'")

    if places_service is None:
        raise HTTPException(
            status_code=500,
            detail="places_key_missing: GOOGLE_PLACES_API_KEY not configured"
        )

    try:
        response = await places_service.place_details(request.placeId)

        logger.info(
            f"Places details result: name='{response.name}', "
            f"phoneE164={response.phoneE164 or 'None'}, "
            f"error={response.error}"
        )

        return response

    except Exception as e:
        logger.error(f"Places details error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"places_details_failed: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
