"""Task service logic."""

from __future__ import annotations

from uuid import UUID

from configs.data_collection import DataCollectionConfig
from configs.tasks import Task
from models.task import TaskResponse
from repos.tasks import TaskRepo


class TaskService:
    """Service for managing tasks.

    Tasks are read-only and loaded from YAML configuration.
    """

    def __init__(self, repo: TaskRepo, config: DataCollectionConfig) -> None:
        """Initialize TaskService with a TaskRepo and config."""
        self.repo: TaskRepo = repo
        self.config: DataCollectionConfig = config

    def get_task_by_id(self, task_id: UUID) -> TaskResponse | None:
        """Get a task by id and return TaskResponse or None."""
        task: Task | None = self.repo.get_by_id(task_id)
        if task is None:
            return None
        return TaskResponse(
            task_id=task.id,
            name=task.name,
            description=task.description,
            version=task.version,
            language_instructions=task.language_instructions,
            metadata=task.metadata,
        )

    def get_tasks(self, name: str | None = None, limit: int = 100, offset: int = 0) -> list[TaskResponse]:
        """Get tasks and map to TaskResponse."""
        tasks: list[Task] = self.repo.get_all(name=name, limit=limit, offset=offset)
        return [
            TaskResponse(
                task_id=t.id,
                name=t.name,
                description=t.description,
                version=t.version,
                language_instructions=t.language_instructions,
                metadata=t.metadata,
            )
            for t in tasks
        ]
