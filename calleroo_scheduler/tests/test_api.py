"""
API endpoint tests for the Scheduler Service.
"""

import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.database import init_database, close_database, get_session, ScheduledTask
from app.models import TaskStatus


@pytest.fixture(autouse=True)
async def setup_database():
    """Set up test database before each test."""
    import os
    os.environ["DATABASE_PATH"] = ":memory:"

    # We need to reset the database module's cached engine
    from app import database
    database._async_engine = None
    database._async_session_factory = None

    await init_database()
    yield
    await close_database()


@pytest.fixture
async def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint returns healthy status."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_create_task_direct_mode(client: AsyncClient):
    """Test creating a task in DIRECT mode."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv-123",
        "mode": "DIRECT",
        "payload": {
            "placeId": "place-abc-123",
            "phoneE164": "+61731824583",
            "scriptPreview": "Hello, I'm calling to check stock...",
            "slots": {"product": "BBQ Chicken"}
        }
    }

    response = await client.post("/tasks", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "taskId" in data
    assert data["status"] == "SCHEDULED"


@pytest.mark.asyncio
async def test_create_task_brief_start_mode(client: AsyncClient):
    """Test creating a task in BRIEF_START mode."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv-456",
        "mode": "BRIEF_START",
        "payload": {
            "place": {
                "placeId": "place-xyz-789",
                "businessName": "Test Store",
                "phoneE164": "+61731824583"
            },
            "slots": {"product": "BBQ Chicken"}
        }
    }

    response = await client.post("/tasks", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "taskId" in data
    assert data["status"] == "SCHEDULED"


@pytest.mark.asyncio
async def test_create_task_direct_mode_missing_script(client: AsyncClient):
    """Test that DIRECT mode requires scriptPreview."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv",
        "mode": "DIRECT",
        "payload": {
            "placeId": "place-abc",
            "phoneE164": "+61731824583",
            # Missing scriptPreview
            "slots": {}
        }
    }

    response = await client.post("/tasks", json=payload)
    assert response.status_code == 400
    assert "scriptPreview" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_brief_start_mode_missing_place(client: AsyncClient):
    """Test that BRIEF_START mode requires place."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv",
        "mode": "BRIEF_START",
        "payload": {
            # Missing place
            "slots": {}
        }
    }

    response = await client.post("/tasks", json=payload)
    assert response.status_code == 400
    assert "place" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_task(client: AsyncClient):
    """Test getting task details by ID."""
    # First create a task
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    create_payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv-get",
        "mode": "DIRECT",
        "payload": {
            "placeId": "place-abc",
            "phoneE164": "+61731824583",
            "scriptPreview": "Hello...",
            "slots": {}
        }
    }

    create_response = await client.post("/tasks", json=create_payload)
    task_id = create_response.json()["taskId"]

    # Now get the task
    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200

    data = response.json()
    assert data["taskId"] == task_id
    assert data["status"] == "SCHEDULED"
    assert data["agentType"] == "STOCK_CHECKER"
    assert data["conversationId"] == "test-conv-get"
    assert len(data["events"]) >= 1  # Should have creation event


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    """Test getting a non-existent task returns 404."""
    response = await client.get("/tasks/non-existent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_task(client: AsyncClient):
    """Test canceling a scheduled task."""
    # First create a task
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    create_payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv-cancel",
        "mode": "DIRECT",
        "payload": {
            "placeId": "place-abc",
            "phoneE164": "+61731824583",
            "scriptPreview": "Hello...",
            "slots": {}
        }
    }

    create_response = await client.post("/tasks", json=create_payload)
    task_id = create_response.json()["taskId"]

    # Cancel the task
    response = await client.post(f"/tasks/{task_id}/cancel")
    assert response.status_code == 200

    data = response.json()
    assert data["taskId"] == task_id
    assert data["status"] == "CANCELED"

    # Verify task is canceled
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.json()["status"] == "CANCELED"


@pytest.mark.asyncio
async def test_cancel_task_not_found(client: AsyncClient):
    """Test canceling a non-existent task returns 404."""
    response = await client.post("/tasks/non-existent-id/cancel")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks(client: AsyncClient):
    """Test listing tasks."""
    # Create a couple of tasks
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    for i in range(3):
        payload = {
            "runAtUtc": future_time,
            "backendBaseUrl": "https://api.callerooapp.com",
            "agentType": "STOCK_CHECKER",
            "conversationId": f"test-conv-list-{i}",
            "mode": "DIRECT",
            "payload": {
                "placeId": "place-abc",
                "phoneE164": "+61731824583",
                "scriptPreview": "Hello...",
                "slots": {}
            }
        }
        await client.post("/tasks", json=payload)

    # List all tasks
    response = await client.get("/tasks")
    assert response.status_code == 200

    data = response.json()
    assert len(data) >= 3


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client: AsyncClient):
    """Test listing tasks filtered by status."""
    future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    # Create a task
    payload = {
        "runAtUtc": future_time,
        "backendBaseUrl": "https://api.callerooapp.com",
        "agentType": "STOCK_CHECKER",
        "conversationId": "test-conv-filter",
        "mode": "DIRECT",
        "payload": {
            "placeId": "place-abc",
            "phoneE164": "+61731824583",
            "scriptPreview": "Hello...",
            "slots": {}
        }
    }
    create_response = await client.post("/tasks", json=payload)
    task_id = create_response.json()["taskId"]

    # Cancel it
    await client.post(f"/tasks/{task_id}/cancel")

    # List only CANCELED tasks
    response = await client.get("/tasks?status=CANCELED")
    assert response.status_code == 200

    data = response.json()
    assert all(t["status"] == "CANCELED" for t in data)
