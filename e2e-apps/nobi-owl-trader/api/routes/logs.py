from fastapi import APIRouter, Query
from typing import List, Optional
from api.models import LogEntry, LogRepository

router = APIRouter(prefix="/api/logs", tags=["Logs"])
repo = LogRepository()

@router.get("/", response_model=List[LogEntry])
async def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    level: Optional[str] = Query(default=None)
):
    """Retrieve execution logs from the database"""
    return repo.get_all(limit=limit, offset=offset, level=level)

@router.delete("/clear")
async def clear_logs(days: int = Query(default=0, ge=0)):
    """Clear logs older than X days (or all logs if days=0)"""
    repo.clear(days=days)
    if days <= 0:
        return {"status": "success", "message": "Cleared all logs"}
    return {"status": "success", "message": f"Cleared logs older than {days} days"}
