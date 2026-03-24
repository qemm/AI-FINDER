from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ai_finder.storage import Storage
from backend.config import Settings, get_settings

router = APIRouter(prefix="/export", tags=["export"])


def _get_storage(settings: Settings = Depends(get_settings)) -> Storage:
    return Storage(db_path=settings.db_path)


@router.get("/json")
async def export_json(
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(_get_storage),
) -> FileResponse:
    try:
        storage.export_json(settings.export_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not os.path.exists(settings.export_path):
        raise HTTPException(status_code=500, detail="Export file was not created")

    return FileResponse(
        path=settings.export_path,
        media_type="application/json",
        filename="ai_finder_export.json",
    )
