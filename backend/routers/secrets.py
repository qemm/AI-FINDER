from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends

from ai_finder.storage import Storage
from backend.config import Settings, get_settings
from backend.schemas import Page, SecretFinding, SecretRuleStat

router = APIRouter(tags=["secrets"])


def _get_storage(settings: Settings = Depends(get_settings)) -> Storage:
    return Storage(db_path=settings.db_path)


@router.get("/secrets", response_model=Page[SecretFinding])
async def list_secrets(
    rule_name: Optional[str] = None,
    platform: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    storage: Storage = Depends(_get_storage),
) -> Page[SecretFinding]:
    rows = storage.list_secrets(rule_name=rule_name, platform=platform, page=page, page_size=page_size)
    total = storage.count_secrets(rule_name=rule_name, platform=platform)
    return Page(items=[SecretFinding(**r) for r in rows], total=total, page=page, page_size=page_size)


@router.get("/secrets/stats", response_model=list[SecretRuleStat])
async def secrets_stats(
    storage: Storage = Depends(_get_storage),
) -> list[SecretRuleStat]:
    rows = storage.secrets_by_rule()
    return [SecretRuleStat(**r) for r in rows]
