"""
Tests for the filler/poll pattern in Twilio endpoints.

These tests verify:
1. /twilio/gather returns immediate filler + redirect to /twilio/poll
2. /twilio/poll returns Gather when response is ready
3. /twilio/poll continues polling when response not ready
4. /twilio/poll hangs up after timeout
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.twilio_service import CallRun, CALL_RUNS


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_call_run():
    """Create a sample CallRun for testing."""
    call_run = CallRun(
        call_id="CA123456789",
        conversation_id="test-conv-123",
        agent_type="STOCK_CHECKER",
        phone_e164="+61400000000",
        script_preview="Check stock availability",
        slots={"product_name": "Test Product"},
        status="in-progress",
        turn=0,
        retry=0,
        live_transcript=[],
    )
    CALL_RUNS[call_run.call_id] = call_run
    yield call_run
    # Cleanup
    if call_run.call_id in CALL_RUNS:
        del CALL_RUNS[call_run.call_id]


class TestTwilioGatherFiller:
    """Tests for /twilio/gather with filler pattern."""

    def test_gather_returns_immediate_redirect(self, client, sample_call_run):
        """Verify that /twilio/gather returns filler + redirect to /twilio/poll."""
        with patch("app.main.twilio_service") as mock_service:
            mock_service.generate_agent_response_async = AsyncMock()

            response = client.post(
                "/twilio/gather",
                params={
                    "conversationId": sample_call_run.conversation_id,
                    "turn": "0",
                    "retry": "0",
                },
                data={"SpeechResult": "Hello, this is a test"},
            )

            assert response.status_code == 200
            content = response.text

            # Should contain a filler phrase
            assert "<Say" in content
            # Should redirect to /twilio/poll
            assert "/twilio/poll" in content
            assert "attempt=0" in content
            # Should have pause
            assert "<Pause" in content

    def test_gather_silence_retry(self, client, sample_call_run):
        """Verify silence handling still works."""
        response = client.post(
            "/twilio/gather",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "retry": "0",
            },
            data={"SpeechResult": ""},
        )

        assert response.status_code == 200
        content = response.text

        # Should prompt for retry
        assert "I'm sorry, I didn't catch that" in content or "Hello? Is anyone there?" in content
        assert "retry=1" in content

    def test_gather_max_retries_hangup(self, client, sample_call_run):
        """Verify hangup after max silence retries."""
        response = client.post(
            "/twilio/gather",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "retry": "1",  # Already retried once
            },
            data={"SpeechResult": ""},
        )

        assert response.status_code == 200
        content = response.text

        # Should hang up
        assert "<Hangup" in content
        assert "I haven't heard anything" in content


class TestTwilioPoll:
    """Tests for /twilio/poll endpoint."""

    def test_poll_returns_gather_when_ready(self, client, sample_call_run):
        """Verify /twilio/poll returns Gather when response is ready."""
        # Set up pending response
        sample_call_run.pending_agent_reply = "Hello, how can I help you?"
        sample_call_run.pending_started_at = datetime.utcnow()

        response = client.post(
            "/twilio/poll",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "attempt": "0",
            },
        )

        assert response.status_code == 200
        content = response.text

        # Should contain the agent response in a Gather
        assert "<Gather" in content
        assert "Hello, how can I help you?" in content
        # Should redirect to /twilio/gather for next input
        assert "/twilio/gather" in content

        # Pending state should be cleared
        assert sample_call_run.pending_agent_reply is None

    def test_poll_continues_when_not_ready(self, client, sample_call_run):
        """Verify /twilio/poll continues polling when response not ready."""
        # No pending reply yet
        sample_call_run.pending_agent_reply = None
        sample_call_run.pending_started_at = datetime.utcnow()
        sample_call_run.is_generating = True

        response = client.post(
            "/twilio/poll",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "attempt": "0",
            },
        )

        assert response.status_code == 200
        content = response.text

        # Should have a filler phrase
        assert "<Say" in content
        # Should redirect back to poll with incremented attempt
        assert "/twilio/poll" in content
        assert "attempt=1" in content

    def test_poll_resets_attempt_after_3(self, client, sample_call_run):
        """Verify attempt counter resets after 3."""
        sample_call_run.pending_agent_reply = None
        sample_call_run.pending_started_at = datetime.utcnow()

        response = client.post(
            "/twilio/poll",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "attempt": "3",  # At max
            },
        )

        assert response.status_code == 200
        content = response.text

        # Should reset to attempt=0
        assert "attempt=0" in content

    def test_poll_timeout_hangup(self, client, sample_call_run):
        """Verify hangup after timeout (>20 seconds)."""
        # Set started_at to 25 seconds ago
        sample_call_run.pending_agent_reply = None
        sample_call_run.pending_started_at = datetime.utcnow() - timedelta(seconds=25)

        response = client.post(
            "/twilio/poll",
            params={
                "conversationId": sample_call_run.conversation_id,
                "turn": "1",
                "attempt": "0",
            },
        )

        assert response.status_code == 200
        content = response.text

        # Should hang up with apology
        assert "<Hangup" in content
        assert "technical difficulties" in content


class TestTwilioVoice:
    """Tests for /twilio/voice endpoint."""

    def test_voice_waits_for_callee(self, client, sample_call_run):
        """Verify /twilio/voice waits for callee to speak first."""
        response = client.post(
            "/twilio/voice",
            params={"conversationId": sample_call_run.conversation_id},
        )

        assert response.status_code == 200
        content = response.text

        # Should have Gather without initial Say inside
        assert "<Gather" in content
        # turn=0 for initial greeting
        assert "turn=0" in content
        # Should NOT have "Hello, this is Calleroo" as first thing
        # The Gather should be empty (no Say inside before callee speaks)
