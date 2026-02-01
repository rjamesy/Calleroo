"""
Scheduler worker tests with mocked backend calls.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

from app.database import (
    init_database,
    close_database,
    get_session,
    ScheduledTask,
    TaskEvent,
    utc_now_iso,
)
from app.scheduler import SchedulerWorker
from app.models import TaskStatus, TaskMode
from app.backend_client import BackendClient, BackendClientError


@pytest.fixture(autouse=True)
async def setup_database():
    """Set up test database before each test."""
    import os
    os.environ["DATABASE_PATH"] = ":memory:"

    # Reset the database module's cached engine
    from app import database
    database._async_engine = None
    database._async_session_factory = None

    await init_database()
    yield
    await close_database()


async def create_test_task(
    mode: str = "DIRECT",
    run_at_utc: str = None,
    status: str = "SCHEDULED",
    script_preview: str = "Test script",
    place_json: str = None,
) -> str:
    """Helper to create a test task in the database."""
    import uuid

    if run_at_utc is None:
        # Default to past time so it's immediately due
        run_at_utc = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    task_id = str(uuid.uuid4())
    now = utc_now_iso()

    task = ScheduledTask(
        id=task_id,
        status=status,
        created_at=now,
        updated_at=now,
        run_at_utc=run_at_utc,
        agent_type="STOCK_CHECKER",
        conversation_id="test-conv",
        mode=mode,
        place_id="place-123",
        phone_e164="+61731824583",
        script_preview=script_preview if mode == "DIRECT" else None,
        slots_json=json.dumps({"product": "Test Product"}),
        place_json=place_json,
        backend_base_url="https://api.test.com",
    )

    session = await get_session()
    try:
        session.add(task)
        await session.commit()
    finally:
        await session.close()

    return task_id


async def get_task_status(task_id: str) -> dict:
    """Helper to get task status from database."""
    from sqlalchemy import select

    session = await get_session()
    try:
        stmt = select(ScheduledTask).where(ScheduledTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()
        if task:
            return {
                "status": task.status,
                "call_id": task.call_id,
                "last_error": task.last_error,
            }
        return None
    finally:
        await session.close()


async def get_task_events(task_id: str) -> list:
    """Helper to get task events from database."""
    from sqlalchemy import select

    session = await get_session()
    try:
        stmt = select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)
        result = await session.execute(stmt)
        events = result.scalars().all()
        return [{"level": e.level, "message": e.message} for e in events]
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_direct_mode_execution_success():
    """Test DIRECT mode task executes successfully."""
    task_id = await create_test_task(mode="DIRECT")

    # Mock the backend client
    mock_response = AsyncMock()
    mock_response.callId = "twilio-call-123"

    with patch.object(BackendClient, "call_start", return_value=mock_response) as mock_call:
        worker = SchedulerWorker(
            poll_interval=1.0,
            default_backend_url="https://api.test.com",
        )

        # Process due tasks once
        await worker._process_due_tasks()

        # Verify call_start was called
        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert call_args.kwargs["conversation_id"] == "test-conv"
        assert call_args.kwargs["agent_type"] == "STOCK_CHECKER"
        assert call_args.kwargs["script_preview"] == "Test script"

    # Verify task status
    task = await get_task_status(task_id)
    assert task["status"] == "COMPLETED"
    assert task["call_id"] == "twilio-call-123"

    # Verify events
    events = await get_task_events(task_id)
    assert any("started" in e["message"].lower() for e in events)
    assert any("completed" in e["message"].lower() for e in events)


@pytest.mark.asyncio
async def test_brief_start_mode_execution_success():
    """Test BRIEF_START mode task executes successfully."""
    place_data = {
        "placeId": "place-123",
        "businessName": "Test Store",
        "phoneE164": "+61731824583",
    }

    task_id = await create_test_task(
        mode="BRIEF_START",
        place_json=json.dumps(place_data),
    )

    # Mock the backend client
    mock_brief_response = AsyncMock()
    mock_brief_response.scriptPreview = "Generated script from brief"

    mock_start_response = AsyncMock()
    mock_start_response.callId = "twilio-call-456"

    with patch.object(BackendClient, "call_brief", return_value=mock_brief_response) as mock_brief:
        with patch.object(BackendClient, "call_start", return_value=mock_start_response) as mock_start:
            worker = SchedulerWorker(
                poll_interval=1.0,
                default_backend_url="https://api.test.com",
            )

            await worker._process_due_tasks()

            # Verify call_brief was called
            mock_brief.assert_called_once()
            brief_args = mock_brief.call_args
            assert brief_args.kwargs["place"]["placeId"] == "place-123"

            # Verify call_start was called with script from brief
            mock_start.assert_called_once()
            start_args = mock_start.call_args
            assert start_args.kwargs["script_preview"] == "Generated script from brief"

    # Verify task status
    task = await get_task_status(task_id)
    assert task["status"] == "COMPLETED"
    assert task["call_id"] == "twilio-call-456"


@pytest.mark.asyncio
async def test_execution_failure_marks_task_failed():
    """Test that backend errors result in FAILED status."""
    task_id = await create_test_task(mode="DIRECT")

    # Mock backend client to raise error
    with patch.object(
        BackendClient,
        "call_start",
        side_effect=BackendClientError("Backend unavailable", status_code=500),
    ):
        worker = SchedulerWorker(
            poll_interval=1.0,
            default_backend_url="https://api.test.com",
        )

        await worker._process_due_tasks()

    # Verify task status
    task = await get_task_status(task_id)
    assert task["status"] == "FAILED"
    assert "Backend unavailable" in task["last_error"]

    # Verify error event was logged
    events = await get_task_events(task_id)
    assert any(e["level"] == "ERROR" for e in events)


@pytest.mark.asyncio
async def test_scheduled_task_not_due_not_processed():
    """Test that tasks scheduled for future are not processed."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    task_id = await create_test_task(mode="DIRECT", run_at_utc=future_time)

    with patch.object(BackendClient, "call_start") as mock_call:
        worker = SchedulerWorker(
            poll_interval=1.0,
            default_backend_url="https://api.test.com",
        )

        await worker._process_due_tasks()

        # call_start should NOT be called
        mock_call.assert_not_called()

    # Task should still be SCHEDULED
    task = await get_task_status(task_id)
    assert task["status"] == "SCHEDULED"


@pytest.mark.asyncio
async def test_canceled_task_not_processed():
    """Test that canceled tasks are not processed."""
    task_id = await create_test_task(mode="DIRECT", status="CANCELED")

    with patch.object(BackendClient, "call_start") as mock_call:
        worker = SchedulerWorker(
            poll_interval=1.0,
            default_backend_url="https://api.test.com",
        )

        await worker._process_due_tasks()

        # call_start should NOT be called
        mock_call.assert_not_called()


@pytest.mark.asyncio
async def test_notification_stub_logged():
    """Test that notification stub is logged for tasks with notify_target."""
    import uuid

    task_id = str(uuid.uuid4())
    now = utc_now_iso()
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    task = ScheduledTask(
        id=task_id,
        status="SCHEDULED",
        created_at=now,
        updated_at=now,
        run_at_utc=past_time,
        agent_type="STOCK_CHECKER",
        conversation_id="test-conv",
        mode="DIRECT",
        place_id="place-123",
        phone_e164="+61731824583",
        script_preview="Test script",
        slots_json="{}",
        backend_base_url="https://api.test.com",
        notify_target="user-123",  # Set notify target
    )

    session = await get_session()
    try:
        session.add(task)
        await session.commit()
    finally:
        await session.close()

    # Mock successful call
    mock_response = AsyncMock()
    mock_response.callId = "twilio-call-789"

    with patch.object(BackendClient, "call_start", return_value=mock_response):
        worker = SchedulerWorker(
            poll_interval=1.0,
            default_backend_url="https://api.test.com",
        )

        await worker._process_due_tasks()

    # Verify notification stub was logged
    events = await get_task_events(task_id)
    assert any("NOTIFY_STUB" in e["message"] and "user-123" in e["message"] for e in events)


@pytest.mark.asyncio
async def test_worker_start_stop():
    """Test that worker can be started and stopped."""
    worker = SchedulerWorker(poll_interval=0.1)

    await worker.start()
    assert worker._running is True

    await worker.stop()
    assert worker._running is False
