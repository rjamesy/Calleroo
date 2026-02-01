"""
FastAPI application for the Calleroo Scheduler Service.

Provides endpoints for creating, managing, and monitoring scheduled call tasks.
"""

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, update

from .database import (
    ScheduledTask,
    TaskEvent,
    close_database,
    get_session,
    init_database,
    utc_now_iso,
)
from .models import (
    CancelTaskResponse,
    CreateTaskRequest,
    CreateTaskResponse,
    ErrorResponse,
    HealthResponse,
    TaskEventResponse,
    TaskMode,
    TaskResponse,
    TaskStatus,
)
from .scheduler import SchedulerWorker

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration
VERSION = "1.0.0"
DEFAULT_BACKEND_URL = os.environ.get("DEFAULT_BACKEND_BASE_URL", "https://api.callerooapp.com")
BACKEND_AUTH_TOKEN = os.environ.get("BACKEND_INTERNAL_TOKEN")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "3.0"))

# Global scheduler worker
scheduler_worker: Optional[SchedulerWorker] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global scheduler_worker

    # Startup
    logger.info("Starting Calleroo Scheduler Service...")

    # Initialize database
    await init_database()
    logger.info("Database initialized")

    # Start scheduler worker
    scheduler_worker = SchedulerWorker(
        poll_interval=POLL_INTERVAL,
        default_backend_url=DEFAULT_BACKEND_URL,
        default_auth_token=BACKEND_AUTH_TOKEN,
    )
    await scheduler_worker.start()

    yield

    # Shutdown
    logger.info("Shutting down Calleroo Scheduler Service...")

    if scheduler_worker:
        await scheduler_worker.stop()

    await close_database()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Calleroo Scheduler Service",
    description="Schedule and execute Calleroo phone calls at specified times",
    version=VERSION,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", version=VERSION)


# =============================================================================
# Task Management Endpoints
# =============================================================================


@app.post("/tasks", response_model=CreateTaskResponse, responses={400: {"model": ErrorResponse}})
async def create_task(request: CreateTaskRequest) -> CreateTaskResponse:
    """
    Create a new scheduled task.

    The task will be executed at the specified runAtUtc time.

    **Modes:**
    - DIRECT: Uses the provided scriptPreview to call /call/start directly
    - BRIEF_START: Calls /call/brief first to generate scriptPreview, then /call/start
    """
    task_id = str(uuid.uuid4())
    now = utc_now_iso()

    # Validate payload based on mode
    payload = request.payload

    if request.mode == TaskMode.DIRECT:
        if "scriptPreview" not in payload:
            raise HTTPException(
                status_code=400,
                detail="DIRECT mode requires 'scriptPreview' in payload"
            )
        if "placeId" not in payload or "phoneE164" not in payload:
            raise HTTPException(
                status_code=400,
                detail="DIRECT mode requires 'placeId' and 'phoneE164' in payload"
            )

    elif request.mode == TaskMode.BRIEF_START:
        if "place" not in payload:
            raise HTTPException(
                status_code=400,
                detail="BRIEF_START mode requires 'place' in payload"
            )

    # Create task record
    task = ScheduledTask(
        id=task_id,
        status=TaskStatus.SCHEDULED.value,
        created_at=now,
        updated_at=now,
        run_at_utc=request.runAtUtc,
        timezone=request.timezone,
        agent_type=request.agentType,
        conversation_id=request.conversationId,
        mode=request.mode.value,
        place_id=payload.get("placeId"),
        phone_e164=payload.get("phoneE164"),
        script_preview=payload.get("scriptPreview"),
        slots_json=json.dumps(payload.get("slots", {})),
        place_json=json.dumps(payload.get("place")) if payload.get("place") else None,
        disclosure_json=json.dumps(payload.get("disclosure")) if payload.get("disclosure") else None,
        fallbacks_json=json.dumps(payload.get("fallbacks")) if payload.get("fallbacks") else None,
        backend_base_url=request.backendBaseUrl,
        backend_auth_token=request.backendAuthToken,
        notify_target=request.notifyTarget,
    )

    session = await get_session()
    try:
        session.add(task)

        # Add creation event
        event = TaskEvent(
            task_id=task_id,
            ts_utc=now,
            level="INFO",
            message=f"Task created. Scheduled for {request.runAtUtc}",
        )
        session.add(event)

        await session.commit()
        logger.info(f"Created task {task_id} scheduled for {request.runAtUtc}")

    finally:
        await session.close()

    return CreateTaskResponse(taskId=task_id, status=TaskStatus.SCHEDULED.value)


@app.get("/tasks/{task_id}", response_model=TaskResponse, responses={404: {"model": ErrorResponse}})
async def get_task(task_id: str) -> TaskResponse:
    """Get task details by ID."""
    session = await get_session()
    try:
        # Get task
        stmt = select(ScheduledTask).where(ScheduledTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        # Get events
        events_stmt = (
            select(TaskEvent)
            .where(TaskEvent.task_id == task_id)
            .order_by(TaskEvent.id)
        )
        events_result = await session.execute(events_stmt)
        events = events_result.scalars().all()

        return TaskResponse(
            taskId=task.id,
            status=task.status,
            runAtUtc=task.run_at_utc,
            agentType=task.agent_type,
            conversationId=task.conversation_id,
            mode=task.mode,
            placeId=task.place_id,
            phoneE164=task.phone_e164,
            callId=task.call_id,
            lastError=task.last_error,
            createdAt=task.created_at,
            updatedAt=task.updated_at,
            events=[
                TaskEventResponse(
                    id=e.id,
                    tsUtc=e.ts_utc,
                    level=e.level,
                    message=e.message,
                )
                for e in events
            ],
        )

    finally:
        await session.close()


@app.post(
    "/tasks/{task_id}/cancel",
    response_model=CancelTaskResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def cancel_task(task_id: str) -> CancelTaskResponse:
    """
    Cancel a scheduled task.

    Only tasks with status SCHEDULED can be canceled.
    Tasks that are RUNNING, COMPLETED, FAILED, or already CANCELED cannot be canceled.
    """
    session = await get_session()
    try:
        # Get current task status
        stmt = select(ScheduledTask).where(ScheduledTask.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        if task.status != TaskStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel task with status {task.status}. Only SCHEDULED tasks can be canceled."
            )

        # Update status
        now = utc_now_iso()
        update_stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(status=TaskStatus.CANCELED.value, updated_at=now)
        )
        await session.execute(update_stmt)

        # Add event
        event = TaskEvent(
            task_id=task_id,
            ts_utc=now,
            level="INFO",
            message="Task canceled by user request",
        )
        session.add(event)

        await session.commit()
        logger.info(f"Canceled task {task_id}")

        return CancelTaskResponse(
            taskId=task_id,
            status=TaskStatus.CANCELED.value,
            message="Task canceled successfully",
        )

    finally:
        await session.close()


# =============================================================================
# Debug/Admin Endpoints (optional, for testing)
# =============================================================================


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
) -> list[TaskResponse]:
    """
    List tasks, optionally filtered by status.

    This is a convenience endpoint for debugging/monitoring.
    """
    session = await get_session()
    try:
        stmt = select(ScheduledTask).order_by(ScheduledTask.created_at.desc()).limit(limit)

        if status:
            stmt = stmt.where(ScheduledTask.status == status)

        result = await session.execute(stmt)
        tasks = result.scalars().all()

        responses = []
        for task in tasks:
            # Get events for each task
            events_stmt = (
                select(TaskEvent)
                .where(TaskEvent.task_id == task.id)
                .order_by(TaskEvent.id)
            )
            events_result = await session.execute(events_stmt)
            events = events_result.scalars().all()

            responses.append(
                TaskResponse(
                    taskId=task.id,
                    status=task.status,
                    runAtUtc=task.run_at_utc,
                    agentType=task.agent_type,
                    conversationId=task.conversation_id,
                    mode=task.mode,
                    placeId=task.place_id,
                    phoneE164=task.phone_e164,
                    callId=task.call_id,
                    lastError=task.last_error,
                    createdAt=task.created_at,
                    updatedAt=task.updated_at,
                    events=[
                        TaskEventResponse(
                            id=e.id,
                            tsUtc=e.ts_utc,
                            level=e.level,
                            message=e.message,
                        )
                        for e in events
                    ],
                )
            )

        return responses

    finally:
        await session.close()
