from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from ai_finder.storage import Storage
from backend.config import Settings, get_settings
from backend.schemas import FileDetail, FileRecord, Page, SecretFinding

router = APIRouter(prefix="/files", tags=["files"])


def _get_storage(settings: Settings = Depends(get_settings)) -> Storage:
    return Storage(db_path=settings.db_path)


@router.get("", response_model=Page[FileRecord])
async def list_files(
    platform: Optional[str] = None,
    has_secrets: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    storage: Storage = Depends(_get_storage),
) -> Page[FileRecord]:
    rows = storage.list_files(platform=platform, has_secrets=has_secrets, page=page, page_size=page_size)
    total = storage.count_files(platform=platform, has_secrets=has_secrets)
    return Page(items=[FileRecord(**r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/{file_id}", response_model=FileDetail)
async def get_file(
    file_id: int,
    storage: Storage = Depends(_get_storage),
) -> FileDetail:
    row = storage.get_file(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    findings = storage.get_file_secrets(file_id)
    return FileDetail(
        **{k: v for k, v in row.items()},
        secrets=[SecretFinding(**f) for f in findings],
    )


@router.get("/{file_id}/secrets", response_model=list[SecretFinding])
async def get_file_secrets(
    file_id: int,
    storage: Storage = Depends(_get_storage),
) -> list[SecretFinding]:
    row = storage.get_file(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    findings = storage.get_file_secrets(file_id)
    return [SecretFinding(**f) for f in findings]
