from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_finder.storage import Storage
from backend.config import get_settings
from backend.routers import export, files, jobs, search, secrets
from backend.schemas import DashboardStats, PlatformStat, SecretRuleStat

_settings = get_settings()

app = FastAPI(title="AI-FINDER API", version="1.0.0")

# ---------------------------------------------------------------------------
# CORS — must be added before any route definitions
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(jobs.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(secrets.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(export.router, prefix="/api")


# ---------------------------------------------------------------------------
# Utility endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/stats", response_model=DashboardStats)
async def stats() -> DashboardStats:
    storage = Storage(db_path=_settings.db_path)
    total_files = storage.count()
    total_secrets = storage.count_secrets()
    files_with_secrets = storage.count_files(has_secrets=True)
    platforms_raw = storage.platform_stats()
    rules_raw = storage.secrets_by_rule()
    return DashboardStats(
        total_files=total_files,
        total_secrets=total_secrets,
        files_with_secrets=files_with_secrets,
        platforms=[PlatformStat(**p) for p in platforms_raw],
        secrets_by_rule=[SecretRuleStat(**r) for r in rules_raw],
    )
