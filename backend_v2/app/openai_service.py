"""
OpenAI service for conversation management.
This is the SOLE authority for conversation flow.

Python 3.9 compatible - uses typing.Dict, typing.List, typing.Optional
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from .models import (
    AgentType,
    ChatMessage,
    Choice,
    Confidence,
    ConfirmationCard,
    ConversationResponse,
    InputType,
    NextAction,
    Question,
)
from .prompts import get_system_prompt

logger = logging.getLogger(__name__)

# Maximum chars to log from OpenAI response on error
MAX_ERROR_LOG_CHARS = 2000


class OpenAIService:
    """Service for calling OpenAI to drive conversation flow."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

        self.client = AsyncOpenAI(api_key=api_key)
        # Default to gpt-4o-mini for cost/speed balance
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        logger.info(f"OpenAI service configured with model: {self.model}")

    async def get_next_turn(
        self,
        agent_type: AgentType,
        user_message: str,
        slots: Dict[str, Any],
        message_history: List[ChatMessage],
    ) -> ConversationResponse:
        """
        Call OpenAI to determine the next turn in the conversation.

        This method ALWAYS calls OpenAI - no caching, no local heuristics.
        OpenAI is the sole authority for conversation flow.
        """
        system_prompt = get_system_prompt(agent_type.value)

        # Build context message with current slots
        context = self._build_context(slots, message_history)

        # Build messages for OpenAI
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": context},
        ]

        # Add message history
        for msg in message_history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current user message if not empty (empty = start of conversation)
        if user_message:
            messages.append({"role": "user", "content": user_message})
        else:
            # Starting conversation - ask OpenAI to begin
            messages.append({
                "role": "user",
                "content": "[START_CONVERSATION] Please greet the user and ask the first question."
            })

        logger.info(f"Calling OpenAI ({self.model}) with {len(messages)} messages")

        # ALWAYS call OpenAI - no shortcuts
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        logger.debug(f"OpenAI raw response: {content[:500]}...")

        # Parse and validate the response
        return self._parse_response(content, self.model)

    def _build_context(
        self,
        slots: Dict[str, Any],
        message_history: List[ChatMessage]
    ) -> str:
        """Build a context message with current slots for OpenAI."""
        context_parts = ["CURRENT STATE:"]

        if slots:
            context_parts.append(f"Collected slots: {json.dumps(slots)}")
        else:
            context_parts.append("Collected slots: (none yet)")

        context_parts.append(f"Message count: {len(message_history)}")

        return "\n".join(context_parts)

    def _parse_response(self, content: Optional[str], model: str) -> ConversationResponse:
        """
        Parse OpenAI JSON response into ConversationResponse.

        Raises exception on invalid JSON - NO local fallback.
        """
        if not content:
            raise ValueError("OpenAI returned empty response")

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            # Log truncated response for debugging
            truncated = content[:MAX_ERROR_LOG_CHARS] if len(content) > MAX_ERROR_LOG_CHARS else content
            logger.error(f"invalid_openai_json: Failed to parse response: {truncated}")
            raise ValueError(f"invalid_openai_json: OpenAI returned invalid JSON: {str(e)}")

        # Validate required fields
        if "assistantMessage" not in data:
            raise ValueError("invalid_openai_json: Missing 'assistantMessage' field")
        if "nextAction" not in data:
            raise ValueError("invalid_openai_json: Missing 'nextAction' field")

        # Parse question if present
        question: Optional[Question] = None
        if data.get("question"):
            q = data["question"]
            choices: Optional[List[Choice]] = None
            if q.get("choices"):
                choices = [
                    Choice(label=c["label"], value=c["value"])
                    for c in q["choices"]
                ]
            question = Question(
                text=q.get("text", ""),
                field=q.get("field", "unknown"),
                inputType=InputType(q.get("inputType", "TEXT")),
                choices=choices,
                optional=q.get("optional", False),
            )

        # Parse confirmation card if present
        confirmation_card: Optional[ConfirmationCard] = None
        if data.get("confirmationCard"):
            cc = data["confirmationCard"]
            confirmation_card = ConfirmationCard(
                title=cc.get("title", "Confirmation"),
                lines=cc.get("lines", []),
                confirmLabel=cc.get("confirmLabel", "Yes"),
                rejectLabel=cc.get("rejectLabel", "Not quite"),
            )

        return ConversationResponse(
            assistantMessage=data.get("assistantMessage", ""),
            nextAction=NextAction(data.get("nextAction", "ASK_QUESTION")),
            question=question,
            extractedData=data.get("extractedData"),
            confidence=Confidence(data.get("confidence", "MEDIUM")),
            confirmationCard=confirmation_card,
            aiCallMade=True,  # We got here, so OpenAI was called
            aiModel=model,
        )
