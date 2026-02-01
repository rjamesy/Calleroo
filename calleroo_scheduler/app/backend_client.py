"""
HTTP client for calling backend_v2 APIs.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from .models import (
    BackendCallBriefRequest,
    BackendCallBriefResponse,
    BackendCallStartRequest,
    BackendCallStartResponse,
)

logger = logging.getLogger(__name__)


class BackendClientError(Exception):
    """Raised when a backend API call fails."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_body: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BackendClient:
    """
    HTTP client for calling backend_v2 APIs.

    Supports optional authentication via X-Calleroo-Internal-Token header.
    """

    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """
        Initialize the backend client.

        Args:
            base_url: Base URL of the backend (e.g., https://api.callerooapp.com)
            auth_token: Optional internal auth token
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.auth_token:
            headers["X-Calleroo-Internal-Token"] = self.auth_token
        return headers

    async def call_brief(
        self,
        conversation_id: str,
        agent_type: str,
        place: Dict[str, Any],
        slots: Dict[str, Any],
        disclosure: Optional[Dict[str, Any]] = None,
        fallbacks: Optional[Dict[str, Any]] = None,
    ) -> BackendCallBriefResponse:
        """
        Call the backend /call/brief endpoint.

        Args:
            conversation_id: Conversation identifier
            agent_type: Type of agent (e.g., STOCK_CHECKER)
            place: Place data with placeId, businessName, phoneE164
            slots: Slot values collected from user
            disclosure: Optional disclosure settings
            fallbacks: Optional fallback settings

        Returns:
            BackendCallBriefResponse with scriptPreview

        Raises:
            BackendClientError: If the API call fails
        """
        url = f"{self.base_url}/call/brief"

        payload = {
            "conversationId": conversation_id,
            "agentType": agent_type,
            "place": place,
            "slots": slots or {},
        }
        if disclosure:
            payload["disclosure"] = disclosure
        if fallbacks:
            payload["fallbacks"] = fallbacks

        logger.info(f"Calling /call/brief for conversation {conversation_id}")
        logger.debug(f"Request payload: {payload}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                )

            if response.status_code != 200:
                error_msg = f"Backend /call/brief failed with status {response.status_code}"
                logger.error(f"{error_msg}: {response.text}")
                raise BackendClientError(
                    error_msg,
                    status_code=response.status_code,
                    response_body=response.text,
                )

            data = response.json()
            logger.info(f"Successfully got script preview for conversation {conversation_id}")
            return BackendCallBriefResponse(**data)

        except httpx.RequestError as e:
            error_msg = f"Network error calling /call/brief: {str(e)}"
            logger.error(error_msg)
            raise BackendClientError(error_msg)

    async def call_start(
        self,
        conversation_id: str,
        agent_type: str,
        place_id: str,
        phone_e164: str,
        script_preview: str,
        slots: Dict[str, Any],
    ) -> BackendCallStartResponse:
        """
        Call the backend /call/start endpoint.

        Args:
            conversation_id: Conversation identifier
            agent_type: Type of agent
            place_id: Google Place ID
            phone_e164: Phone number in E.164 format
            script_preview: The script for the agent to follow
            slots: Slot values

        Returns:
            BackendCallStartResponse with callId

        Raises:
            BackendClientError: If the API call fails
        """
        url = f"{self.base_url}/call/start"

        payload = {
            "conversationId": conversation_id,
            "agentType": agent_type,
            "placeId": place_id,
            "phoneE164": phone_e164,
            "scriptPreview": script_preview,
            "slots": slots or {},
        }

        logger.info(f"Calling /call/start for conversation {conversation_id}")
        logger.debug(f"Request payload: {payload}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                )

            if response.status_code != 200:
                error_msg = f"Backend /call/start failed with status {response.status_code}"
                logger.error(f"{error_msg}: {response.text}")
                raise BackendClientError(
                    error_msg,
                    status_code=response.status_code,
                    response_body=response.text,
                )

            data = response.json()
            logger.info(f"Successfully started call {data.get('callId')} for conversation {conversation_id}")
            return BackendCallStartResponse(**data)

        except httpx.RequestError as e:
            error_msg = f"Network error calling /call/start: {str(e)}"
            logger.error(error_msg)
            raise BackendClientError(error_msg)

    async def health_check(self) -> bool:
        """
        Check if the backend is healthy.

        Returns:
            True if backend responds to /health, False otherwise
        """
        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self._get_headers())
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Backend health check failed: {e}")
            return False
