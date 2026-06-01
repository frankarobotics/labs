"""Configuration for tasks loaded from YAML."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_yaml import parse_yaml_file_as


class Task(BaseModel):
    """Configuration for a single task."""

    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: UUID
    name: str = Field(..., max_length=128, min_length=1)
    description: str | None = None
    version: str | None = Field(None, max_length=64)
    language_instructions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


DUMMY_TASK = Task(
    id=UUID("00000000-0000-0000-0000-000000000000"),
    name="dummy task",
    description="No task available. You can add tasks in the tasks configuration file of your deployment.",
)


class TasksConfig(BaseModel):
    """Configuration for all tasks."""

    TASKS_CONFIG_PATH: str = "config_tasks.yml"

    tasks: list[Task] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, file_path: str = TASKS_CONFIG_PATH) -> TasksConfig:
        """Load tasks configuration from a YAML file.

        Args:
            file_path: Path to the YAML configuration file. Defaults to TASKS_CONFIG_PATH.

        Returns:
            A TasksConfig instance loaded from the YAML file.
            If the file is invalid or cannot be read, returns an empty TasksConfig.
        """
        try:
            config: TasksConfig = parse_yaml_file_as(cls, file_path)

            # Validate for duplicate IDs
            task_ids = [task.id for task in config.tasks]
            if len(task_ids) != len(set(task_ids)):
                logger.warning("Duplicate task IDs found in config. Only first occurrence will be used.")
                # Remove duplicates, keeping first occurrence
                seen_ids: set[UUID] = set()
                unique_tasks: list[Task] = []
                for task in config.tasks:
                    if task.id not in seen_ids:
                        unique_tasks.append(task)
                        seen_ids.add(task.id)
                config.tasks = unique_tasks
            if not config.tasks:
                config.tasks = [DUMMY_TASK]
            logger.info(f"Successfully loaded {len(config.tasks)} tasks from {file_path}")
            return config
        except FileNotFoundError:
            logger.warning(f"Tasks configuration file not found: {file_path}. No tasks will be available.")
        except ValidationError as e:
            logger.error(f"Invalid tasks configuration in {file_path}: {e}. No tasks will be available.")
        except Exception as e:
            logger.error(f"Failed to load tasks configuration from {file_path}: {e}. No tasks will be available.")
        return cls(tasks=[DUMMY_TASK])

    def get_task_by_id(self, task_id: UUID) -> Task | None:
        """Get a task by its ID.

        Args:
            task_id: The UUID of the task to retrieve.

        Returns:
            The Task if found, None otherwise.
        """
        return next((task for task in self.tasks if task.id == task_id), None)

    def get_all_tasks(self) -> list[Task]:
        """Get all tasks.

        Returns:
            List of all tasks.
        """
        return self.tasks


def load_tasks_config(file_path: str | None = None) -> TasksConfig:
    """Load tasks configuration from a YAML file.

    Args:
        file_path: Optional path to the YAML configuration file.
                  If None, uses the default TASKS_CONFIG_PATH.

    Returns:
        A TasksConfig instance loaded from the YAML file.
    """
    if file_path is None:
        return TasksConfig.from_yaml()
    return TasksConfig.from_yaml(file_path)
