from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ai_finder.vector_store import VectorStore
from backend.config import Settings, get_settings
from backend.schemas import SemanticSearchResult

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/semantic", response_model=list[SemanticSearchResult])
async def semantic_search(
    q: str = Query(..., min_length=1, description="Search query"),
    n: int = Query(10, ge=1, le=100, description="Number of results"),
    settings: Settings = Depends(get_settings),
) -> list[SemanticSearchResult]:
    vs = VectorStore(persist_directory=settings.vector_db_path)
    raw = vs.search(q, n_results=n)
    results: list[SemanticSearchResult] = []
    for item in raw:
        # distance is L2; convert to a 0-1 similarity score
        distance = item.get("distance", 1.0)
        score = max(0.0, 1.0 - float(distance))
        results.append(
            SemanticSearchResult(
                url=item.get("url", ""),
                platform=item.get("platform", ""),
                tags=item.get("tags", ""),
                score=round(score, 4),
                snippet=item.get("document", ""),
            )
        )
    return results
