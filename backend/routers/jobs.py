from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.config import Settings, get_settings
from backend.job_store import store
from backend.schemas import CrawlJobRequest, JobStatus, ScanJobRequest
from backend.tasks import run_crawl_job, run_scan_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/crawl", response_model=JobStatus, status_code=202)
async def start_crawl(
    request: CrawlJobRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> JobStatus:
    job = store.create()
    background_tasks.add_task(run_crawl_job, job.job_id, request, settings)
    return JobStatus(job_id=job.job_id, status=job.status)


@router.post("/scan", response_model=JobStatus, status_code=202)
async def start_scan(
    request: ScanJobRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> JobStatus:
    job = store.create()
    background_tasks.add_task(run_scan_job, job.job_id, request, settings)
    return JobStatus(job_id=job.job_id, status=job.status)


@router.get("/{job_id}", response_model=JobStatus)
async def get_job(job_id: str) -> JobStatus:
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(job_id=job.job_id, status=job.status, stats=job.stats, error=job.error)


@router.get("/{job_id}/stream")
async def stream_job(job_id: str) -> StreamingResponse:
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(job.queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a keepalive comment
                yield ": keepalive\n\n"
                if job.status in ("done", "error"):
                    break
                continue

            payload = json.dumps(event["data"])
            yield f"event: {event['type']}\ndata: {payload}\n\n"

            if event["type"] in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
