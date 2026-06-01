"""Task endpoints handler."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from loguru import logger

from dependencies import get_task_service
from models.task import TaskResponse
from services.task import TaskService

router: APIRouter = APIRouter()


@router.get("/api/v1/tasks", response_model=list[TaskResponse])
def get_tasks(
    task_service: TaskService = Depends(get_task_service),
    name: str | None = Query(None, description="Filter tasks by exact name"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[TaskResponse]:
    """List tasks with optional name filter."""
    try:
        return task_service.get_tasks(name=name, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Failed to list tasks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {e}") from e


@router.get("/api/v1/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID = Path(...), task_service: TaskService = Depends(get_task_service)) -> TaskResponse:
    """Get a single task by ID."""
    try:
        t: TaskResponse | None = task_service.get_task_by_id(task_id)
        if t is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return t
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get task: {e}") from e
