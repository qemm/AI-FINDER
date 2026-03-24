from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Job:
    job_id: str
    status: str = "queued"   # queued | running | done | error
    stats: dict = field(default_factory=dict)
    error: Optional[str] = None
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)


class JobStore:
    """In-memory registry mapping job_id → Job."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job(job_id=str(uuid.uuid4()))
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def emit(self, job_id: str, event_type: str, data: dict) -> None:
        job = self._jobs.get(job_id)
        if job:
            await job.queue.put({"type": event_type, "data": data})

    def set_running(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "running"

    def set_done(self, job_id: str, stats: dict) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "done"
            job.stats = stats
            job.queue.put_nowait({"type": "done", "data": stats})

    def set_error(self, job_id: str, message: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = "error"
            job.error = message
            job.queue.put_nowait({"type": "error", "data": {"message": message}})


# Singleton used by routers and tasks
store = JobStore()
