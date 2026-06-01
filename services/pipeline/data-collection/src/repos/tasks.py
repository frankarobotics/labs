"""Repository for managing tasks loaded from YAML configuration."""

from __future__ import annotations

from uuid import UUID

from configs.tasks import Task, TasksConfig


class TaskRepo:
    """Repository for managing tasks from YAML configuration.

    This is a read-only repository that loads tasks from a YAML file.
    """

    def __init__(self, config: TasksConfig) -> None:
        """Initialize the task repository with YAML configuration.

        Args:
            config: TasksConfig instance with loaded tasks.
        """
        self.config: TasksConfig = config

    def get_by_id(self, task_id: UUID) -> Task | None:
        """Get a task by its ID.

        Args:
            task_id: UUID of the task to retrieve.

        Returns:
            Task if found, None otherwise.
        """
        return self.config.get_task_by_id(task_id)

    def get_all(self, name: str | None = None, limit: int = 100, offset: int = 0) -> list[Task]:
        """Get all tasks with optional filters.

        Args:
            name: Optional filter by exact task name.
            limit: Maximum number of tasks to return.
            offset: Number of tasks to skip.

        Returns:
            List of tasks matching the criteria.
        """
        tasks = self.config.get_all_tasks()

        # Filter by name if provided
        if name:
            tasks = [task for task in tasks if task.name == name]

        # Apply offset and limit
        return tasks[offset : offset + limit]
