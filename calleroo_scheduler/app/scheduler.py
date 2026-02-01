"""
Background scheduler worker for executing due tasks.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .backend_client import BackendClient, BackendClientError
from .database import ScheduledTask, TaskEvent, get_session, utc_now_iso
from .models import TaskMode, TaskStatus

logger = logging.getLogger(__name__)


class SchedulerWorker:
    """
    Background worker that polls for due tasks and executes them.
    """

    def __init__(
        self,
        poll_interval: float = 3.0,
        default_backend_url: Optional[str] = None,
        default_auth_token: Optional[str] = None,
    ):
        """
        Initialize the scheduler worker.

        Args:
            poll_interval: Seconds between polling for due tasks
            default_backend_url: Default backend URL if not specified per-task
            default_auth_token: Default auth token if not specified per-task
        """
        self.poll_interval = poll_interval
        self.default_backend_url = default_backend_url
        self.default_auth_token = default_auth_token
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the background worker loop."""
        if self._running:
            logger.warning("Scheduler worker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"Scheduler worker started (poll interval: {self.poll_interval}s)")

    async def stop(self):
        """Stop the background worker loop."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Scheduler worker stopped")

    async def _run_loop(self):
        """Main polling loop."""
        while self._running:
            try:
                await self._process_due_tasks()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _process_due_tasks(self):
        """Find and execute all due tasks."""
        session = await get_session()
        try:
            now_utc = datetime.now(timezone.utc).isoformat()

            # Find due tasks
            stmt = select(ScheduledTask).where(
                ScheduledTask.status == TaskStatus.SCHEDULED.value,
                ScheduledTask.run_at_utc <= now_utc,
            )
            result = await session.execute(stmt)
            due_tasks = result.scalars().all()

            if due_tasks:
                logger.info(f"Found {len(due_tasks)} due task(s)")

            for task in due_tasks:
                await self._execute_task(session, task)

        finally:
            await session.close()

    async def _execute_task(self, session: AsyncSession, task: ScheduledTask):
        """Execute a single task."""
        task_id = task.id
        logger.info(f"Executing task {task_id} (mode: {task.mode})")

        # Mark as RUNNING
        await self._update_task_status(session, task_id, TaskStatus.RUNNING)
        await self._log_event(session, task_id, "INFO", "Task execution started")

        try:
            # Get backend client
            backend_url = task.backend_base_url or self.default_backend_url
            auth_token = task.backend_auth_token or self.default_auth_token

            if not backend_url:
                raise ValueError("No backend URL configured for task")

            client = BackendClient(base_url=backend_url, auth_token=auth_token)

            # Execute based on mode
            if task.mode == TaskMode.DIRECT.value:
                call_id = await self._execute_direct(client, task)
            elif task.mode == TaskMode.BRIEF_START.value:
                call_id = await self._execute_brief_start(client, task)
            else:
                raise ValueError(f"Unknown task mode: {task.mode}")

            # Success - update task
            await self._update_task_completed(session, task_id, call_id)
            await self._log_event(session, task_id, "INFO", f"Task completed successfully. Call ID: {call_id}")

            # Notification stub
            if task.notify_target:
                await self._log_event(
                    session, task_id, "INFO",
                    f"NOTIFY_STUB: would notify user {task.notify_target} - call completed"
                )

            logger.info(f"Task {task_id} completed successfully. Call ID: {call_id}")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task {task_id} failed: {error_msg}")

            await self._update_task_failed(session, task_id, error_msg)
            await self._log_event(session, task_id, "ERROR", f"Task failed: {error_msg}")

            # Notification stub for failure
            if task.notify_target:
                await self._log_event(
                    session, task_id, "INFO",
                    f"NOTIFY_STUB: would notify user {task.notify_target} - call failed"
                )

    async def _execute_direct(self, client: BackendClient, task: ScheduledTask) -> str:
        """
        Execute a DIRECT mode task.
        Calls /call/start directly with stored scriptPreview.
        """
        if not task.script_preview:
            raise ValueError("DIRECT mode requires scriptPreview")

        slots = json.loads(task.slots_json) if task.slots_json else {}

        response = await client.call_start(
            conversation_id=task.conversation_id,
            agent_type=task.agent_type,
            place_id=task.place_id,
            phone_e164=task.phone_e164,
            script_preview=task.script_preview,
            slots=slots,
        )

        return response.callId

    async def _execute_brief_start(self, client: BackendClient, task: ScheduledTask) -> str:
        """
        Execute a BRIEF_START mode task.
        Calls /call/brief first to get scriptPreview, then /call/start.
        """
        slots = json.loads(task.slots_json) if task.slots_json else {}
        place = json.loads(task.place_json) if task.place_json else {}
        disclosure = json.loads(task.disclosure_json) if task.disclosure_json else None
        fallbacks = json.loads(task.fallbacks_json) if task.fallbacks_json else None

        if not place:
            raise ValueError("BRIEF_START mode requires place data")

        # Step 1: Call /call/brief
        brief_response = await client.call_brief(
            conversation_id=task.conversation_id,
            agent_type=task.agent_type,
            place=place,
            slots=slots,
            disclosure=disclosure,
            fallbacks=fallbacks,
        )

        script_preview = brief_response.scriptPreview

        # Step 2: Call /call/start
        start_response = await client.call_start(
            conversation_id=task.conversation_id,
            agent_type=task.agent_type,
            place_id=task.place_id or place.get("placeId"),
            phone_e164=task.phone_e164 or place.get("phoneE164"),
            script_preview=script_preview,
            slots=slots,
        )

        return start_response.callId

    async def _update_task_status(self, session: AsyncSession, task_id: str, status: TaskStatus):
        """Update task status."""
        stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(status=status.value, updated_at=utc_now_iso())
        )
        await session.execute(stmt)
        await session.commit()

    async def _update_task_completed(self, session: AsyncSession, task_id: str, call_id: str):
        """Update task as completed with call ID."""
        stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(
                status=TaskStatus.COMPLETED.value,
                call_id=call_id,
                updated_at=utc_now_iso(),
            )
        )
        await session.execute(stmt)
        await session.commit()

    async def _update_task_failed(self, session: AsyncSession, task_id: str, error: str):
        """Update task as failed with error message."""
        stmt = (
            update(ScheduledTask)
            .where(ScheduledTask.id == task_id)
            .values(
                status=TaskStatus.FAILED.value,
                last_error=error,
                updated_at=utc_now_iso(),
            )
        )
        await session.execute(stmt)
        await session.commit()

    async def _log_event(self, session: AsyncSession, task_id: str, level: str, message: str):
        """Add an event to the task log."""
        event = TaskEvent(
            task_id=task_id,
            ts_utc=utc_now_iso(),
            level=level,
            message=message,
        )
        session.add(event)
        await session.commit()
