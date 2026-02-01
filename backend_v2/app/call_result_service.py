"""
Call Result Service - Formats call results for UI display.

Uses OpenAI to generate user-friendly summaries of call outcomes.
Python 3.9 compatible.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

# System prompt for formatting call results
CALL_RESULT_FORMAT_PROMPT = """You are a helpful assistant that formats phone call results for display in a mobile app.
This summary is for the CUSTOMER who requested the call (not the business).

Given call information, generate a JSON response with:
1. A short title (2-5 words) summarizing the call outcome
2. A 1-2 sentence plain-English summary of what was learned
3. Bullet points (max 8) highlighting key facts
4. Next steps (1-4 items) the user might want to take
5. A cleaned, readable transcript formatted for humans

RULES:
- The "summary" should be a natural sentence a human would say, e.g.:
  "Red Rooster Browns Plains confirmed they have 8 BBQ chickens in stock at $15.95 each."
- Keep bullets concise (under 80 characters each)
- Do NOT invent facts not present in the input
- If there's an error, include it in bullets
- If extractedFacts exist in outcome, reflect them in bullets
- For successful calls, focus on what was learned
- For failed calls, explain what happened and suggest retrying

TRANSCRIPT FORMATTING RULES:
- Use the EVENT_TRANSCRIPT (with speaker labels) as the source of truth
- Replace "Assistant:" with "Calleroo:" in the output
- Replace "User:" with "Business:" in the output
- REMOVE filler phrases like: "One moment", "Just a sec", "Ummmmmm", "Still checking", "Almost there"
- REMOVE silence handling phrases like: "I didn't hear anything", "Hello? Is anyone there?"
- REMOVE technical phrases like: "Quick note—there may be a brief pause"
- Keep only meaningful conversation turns
- If consecutive turns from the same speaker, merge them
- Format each turn on its own line

Output ONLY valid JSON in this exact format:
{{
  "title": "Call completed successfully",
  "summary": "Business X confirmed they have Y in stock at $Z each.",
  "bullets": [
    "First key point",
    "Second key point"
  ],
  "nextSteps": [
    "Suggested action 1",
    "Suggested action 2"
  ],
  "formattedTranscript": "Business: Hello...\\nCalleroo: Hi..." or null
}}
"""

# Filler phrases to remove from transcript
FILLER_PHRASES_TO_REMOVE = [
    "one moment",
    "just a sec",
    "ummmmmm",
    "ummm, one sec",
    "still checking",
    "almost there",
    "i didn't hear anything",
    "hello? is anyone there?",
    "i still can't hear you",
    "quick note—there may be a brief pause",
    "there may be a brief pause while i process",
]


class CallResultService:
    """Service for formatting call results using OpenAI."""

    def __init__(self) -> None:
        """Initialize the service."""
        api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if api_key:
            self.openai_client: Optional[AsyncOpenAI] = AsyncOpenAI(api_key=api_key)
            logger.info(f"CallResultService configured with model: {self.model}")
        else:
            self.openai_client = None
            logger.warning("CallResultService: OPENAI_API_KEY not set")

    async def format_call_result(
        self,
        agent_type: str,
        call_id: str,
        status: str,
        duration_seconds: Optional[int],
        transcript: Optional[str],
        outcome: Optional[Dict[str, Any]],
        error: Optional[str],
        event_transcript: Optional[List[str]] = None,
        business_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Format call results for display.

        Args:
            agent_type: Type of agent (STOCK_CHECKER, RESTAURANT_RESERVATION)
            call_id: Twilio Call SID
            status: Call status (completed, failed, busy, no-answer, canceled)
            duration_seconds: Call duration in seconds
            transcript: Call transcript from Whisper (fallback)
            outcome: OpenAI analysis with success/summary/extractedFacts
            error: Error message if call failed
            event_transcript: List of speaker-labeled turns (primary source)
            business_name: Name of the business called

        Returns:
            Dict with title, summary, bullets, extractedFacts, nextSteps, formattedTranscript, aiCallMade, aiModel
        """
        # Extract facts from outcome if present
        extracted_facts: Dict[str, Any] = {}
        if outcome and isinstance(outcome, dict):
            extracted_facts = outcome.get("extractedFacts", {})
            if not isinstance(extracted_facts, dict):
                extracted_facts = {}

        # If no transcripts AND no outcome, return deterministic response (no AI call)
        if not transcript and not event_transcript and not outcome:
            return self._generate_deterministic_response(
                status=status,
                duration_seconds=duration_seconds,
                error=error,
                extracted_facts=extracted_facts,
                business_name=business_name,
            )

        # Call OpenAI for formatting
        if not self.openai_client:
            logger.warning("OpenAI not configured, using deterministic response")
            return self._generate_deterministic_response(
                status=status,
                duration_seconds=duration_seconds,
                error=error,
                extracted_facts=extracted_facts,
                business_name=business_name,
            )

        try:
            result = await self._call_openai(
                agent_type=agent_type,
                status=status,
                duration_seconds=duration_seconds,
                transcript=transcript,
                outcome=outcome,
                error=error,
                event_transcript=event_transcript,
                business_name=business_name,
            )
            result["extractedFacts"] = extracted_facts
            result["aiCallMade"] = True
            result["aiModel"] = self.model
            return result

        except Exception as e:
            logger.error(f"OpenAI call failed for call {call_id}: {e}")
            raise RuntimeError(f"call_result_format_failed: {str(e)}")

    async def _call_openai(
        self,
        agent_type: str,
        status: str,
        duration_seconds: Optional[int],
        transcript: Optional[str],
        outcome: Optional[Dict[str, Any]],
        error: Optional[str],
        event_transcript: Optional[List[str]] = None,
        business_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call OpenAI to format the call result."""
        # Build event transcript section (primary source)
        if event_transcript:
            # Pre-clean the event transcript
            cleaned_lines = self._pre_clean_transcript(event_transcript)
            event_transcript_text = "\n".join(cleaned_lines)
        else:
            event_transcript_text = "Not available"

        # Build user message with call details
        user_content = f"""Format the following call result:

Business Name: {business_name or "Unknown business"}
Agent Type: {agent_type}
Status: {status}
Duration: {duration_seconds} seconds
Error: {error or "None"}

Outcome Analysis:
{json.dumps(outcome, indent=2) if outcome else "Not available"}

EVENT_TRANSCRIPT (use this as source of truth for speaker attribution):
{event_transcript_text}

RAW_TRANSCRIPT (fallback only, may have speaker errors):
{transcript if transcript else "Not available"}
"""

        response = await self.openai_client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": CALL_RESULT_FORMAT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from OpenAI")

        result = json.loads(content)

        # Validate required fields
        if "title" not in result or "bullets" not in result or "nextSteps" not in result:
            raise ValueError("Missing required fields in OpenAI response")

        return {
            "title": result["title"],
            "summary": result.get("summary"),
            "bullets": result.get("bullets", [])[:8],  # Max 8 bullets
            "nextSteps": result.get("nextSteps", [])[:4],  # Max 4 next steps
            "formattedTranscript": result.get("formattedTranscript"),
        }

    def _pre_clean_transcript(self, event_transcript: List[str]) -> List[str]:
        """Pre-clean the event transcript by removing filler phrases.

        Only removes truly meaningless filler (like "One moment") not hold acknowledgements.

        Args:
            event_transcript: List of "Speaker: message" strings

        Returns:
            Cleaned list with filler turns removed, speakers renamed
        """
        cleaned = []
        for line in event_transcript:
            # Extract the message part (after the colon)
            if ": " in line:
                speaker, message = line.split(": ", 1)
                message_lower = message.lower().strip().rstrip(".!?,")

                # Skip if the message is purely a filler phrase
                is_filler = message_lower in FILLER_PHRASES_TO_REMOVE

                if not is_filler:
                    # Rename speakers for clarity
                    if speaker == "Assistant":
                        speaker = "Calleroo"
                    elif speaker == "User":
                        speaker = "Business"
                    cleaned.append(f"{speaker}: {message}")
            else:
                cleaned.append(line)

        return cleaned

    def _generate_deterministic_response(
        self,
        status: str,
        duration_seconds: Optional[int],
        error: Optional[str],
        extracted_facts: Dict[str, Any],
        business_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate a deterministic response when no AI is needed."""
        # Build title based on status
        title_map = {
            "completed": "Call completed",
            "failed": "Call failed",
            "busy": "Line was busy",
            "no-answer": "No answer",
            "canceled": "Call canceled",
        }
        title = title_map.get(status, f"Call {status}")

        # Build summary based on status
        business_text = business_name or "the business"
        summary_map = {
            "completed": f"Call to {business_text} completed successfully.",
            "failed": f"Call to {business_text} failed to connect.",
            "busy": f"The line at {business_text} was busy.",
            "no-answer": f"{business_text} did not answer the call.",
            "canceled": f"Call to {business_text} was canceled.",
        }
        summary = summary_map.get(status, f"Call to {business_text} ended with status: {status}")

        # Build bullets
        bullets: List[str] = []

        if duration_seconds is not None:
            minutes = duration_seconds // 60
            seconds = duration_seconds % 60
            if minutes > 0:
                bullets.append(f"Duration: {minutes}m {seconds}s")
            else:
                bullets.append(f"Duration: {seconds} seconds")

        if error:
            bullets.append(f"Error: {error}")

        if status == "completed" and not error:
            bullets.append("Call completed successfully")
        elif status == "busy":
            bullets.append("The recipient's line was busy")
        elif status == "no-answer":
            bullets.append("The call was not answered")
        elif status == "failed":
            bullets.append("The call could not be connected")
        elif status == "canceled":
            bullets.append("The call was canceled before connecting")

        # Build next steps
        next_steps: List[str] = []
        if status in ["failed", "busy", "no-answer"]:
            next_steps.append("Try calling again later")
        if status == "completed":
            next_steps.append("Review the call details")
        next_steps.append("Start a new call")

        return {
            "title": title,
            "summary": summary,
            "bullets": bullets,
            "extractedFacts": extracted_facts,
            "nextSteps": next_steps,
            "formattedTranscript": None,
            "aiCallMade": False,
            "aiModel": self.model,
        }


# Singleton instance
_call_result_service: Optional[CallResultService] = None


def get_call_result_service() -> CallResultService:
    """Get or create the CallResultService singleton."""
    global _call_result_service
    if _call_result_service is None:
        _call_result_service = CallResultService()
    return _call_result_service
