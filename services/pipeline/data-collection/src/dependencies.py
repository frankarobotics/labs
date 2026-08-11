"""Centralized FastAPI dependency providers for services and state machine."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Depends
from fastapi.security import HTTPBearer
from loguru import logger
from pipeline_configs.station import StationConfig, load_station_config

from configs.data_collection import DataCollectionConfig, load_data_collection_config
from configs.data_recorder import DataRecorderConfig, load_data_recorder_config
from configs.tasks import TasksConfig, load_tasks_config
from repos.data_recorder import DataRecorderRepo
from repos.devices import DeviceRepo
from repos.episodes import EpisodeRepo
from repos.tasks import TaskRepo
from services.device import DeviceService
from services.episode import EpisodeService
from services.franka_robot import FrankaRobotService
from services.recording import RecordingService
from services.system import SystemService
from services.task import TaskService
from services.teleop import TeleopService
from state_machine.franka_workflow import FrankaWorkflowStateMachine
from state_machine.recording import RecordingStateMachine
from state_machine.recording_autostop import RecordingAutoStopListener

# Global singleton instances
_device_repo_instance: DeviceRepo | None = None
_robot_service_instance: FrankaRobotService | None = None
_workflow_state_machine_instance: FrankaWorkflowStateMachine | None = None
_recording_state_machine_instance: RecordingStateMachine | None = None
_teleop_service_instance: TeleopService | None = None

# Security
security = HTTPBearer()


def get_data_collection_config() -> DataCollectionConfig:
    """Get the data collection configuration instance."""
    return load_data_collection_config()


@lru_cache
def get_tasks_config() -> TasksConfig:
    """Get the tasks configuration instance.

    Cached to avoid repeated file reads and parsing.
    """
    return load_tasks_config()


def get_data_recorder_repo() -> DataRecorderRepo:
    """Get the data recorder repository instance."""
    config: DataRecorderConfig = load_data_recorder_config()
    return DataRecorderRepo(config)


def get_raw_episode_repo() -> EpisodeRepo:
    """Get the raw episode repository instance (raw_episodes/)."""
    return EpisodeRepo("/workspace/data/raw_episodes/")


def get_processed_episode_repo() -> EpisodeRepo:
    """Get the processed episode repository instance (processed_episodes/)."""
    return EpisodeRepo("/workspace/data/processed_episodes/")


def get_task_repo(tasks_config: TasksConfig = Depends(get_tasks_config)) -> TaskRepo:
    """Get the task repository instance."""
    return TaskRepo(tasks_config)


def get_device_repo() -> DeviceRepo:
    """Get the device repository singleton instance."""
    global _device_repo_instance  # noqa: PLW0603
    if _device_repo_instance is None:
        _device_repo_instance = DeviceRepo()
        logger.info("Initialized DeviceRepo singleton")
    return _device_repo_instance


def get_robot_service() -> FrankaRobotService:
    """Get the robot service singleton instance."""
    global _robot_service_instance  # noqa: PLW0603
    if _robot_service_instance is None:
        station_config: StationConfig = load_station_config()
        _robot_service_instance = FrankaRobotService(station_config)
        logger.info("Initialized FrankaRobotService")
    return _robot_service_instance


def get_workflow_state_machine(
    robot_service: FrankaRobotService = Depends(get_robot_service),
) -> FrankaWorkflowStateMachine:
    """Get the state machine instance."""
    global _workflow_state_machine_instance  # noqa: PLW0603
    if _workflow_state_machine_instance is None:
        _workflow_state_machine_instance = FrankaWorkflowStateMachine(robot_service)
        logger.info("Initialized FrankaWorkflowStateMachine")
    return _workflow_state_machine_instance


def get_teleop_service(
    state_machine: FrankaWorkflowStateMachine = Depends(get_workflow_state_machine),
    robot_service: FrankaRobotService = Depends(get_robot_service),
) -> TeleopService:
    """Get the teleop service instance."""
    global _teleop_service_instance  # noqa: PLW0603
    if _teleop_service_instance is None:
        station_config: StationConfig = load_station_config()
        _teleop_service_instance = TeleopService(station_config, state_machine, robot_service)
        logger.info("Initialized TeleopService")
    return _teleop_service_instance


def get_episode_service(  # noqa: PLR0913
    data_recorder_repo: DataRecorderRepo = Depends(get_data_recorder_repo),
    raw_episode_repo: EpisodeRepo = Depends(get_raw_episode_repo),
    processed_episode_repo: EpisodeRepo = Depends(get_processed_episode_repo),
    task_repo: TaskRepo = Depends(get_task_repo),
    device_repo: DeviceRepo = Depends(get_device_repo),
    config: DataCollectionConfig = Depends(get_data_collection_config),
) -> EpisodeService:
    """Get the episode service instance."""
    station_config: StationConfig = load_station_config()
    return EpisodeService(
        data_recorder_repo,
        raw_episode_repo,
        processed_episode_repo,
        task_repo,
        device_repo,
        station_config,
        config.processed_data_path,
    )


def get_recording_state_machine(
    episode_service: EpisodeService = Depends(get_episode_service),
    data_recorder_repo: DataRecorderRepo = Depends(get_data_recorder_repo),
) -> RecordingStateMachine:
    """Get the state machine instance."""
    global _recording_state_machine_instance  # noqa: PLW0603
    if _recording_state_machine_instance is None:
        _recording_state_machine_instance = RecordingStateMachine(episode_service, data_recorder_repo)
        workflow_state_machine = get_workflow_state_machine()
        workflow_state_machine.add_listener(RecordingAutoStopListener(_recording_state_machine_instance))
        logger.info("Initialized RecordingStateMachine and registered recording auto-stop listener")
    return _recording_state_machine_instance


def get_recording_service(
    state_machine: RecordingStateMachine = Depends(get_recording_state_machine),
    data_recorder_repo: DataRecorderRepo = Depends(get_data_recorder_repo),
    teleop_service: TeleopService = Depends(get_teleop_service),
    workflow_state_machine: FrankaWorkflowStateMachine = Depends(get_workflow_state_machine),
) -> RecordingService:
    """Get the recording service instance."""
    return RecordingService(
        state_machine,
        data_recorder_repo,
        teleop_service,
        workflow_state_machine,
    )


def get_device_service(
    device_repo: DeviceRepo = Depends(get_device_repo),
    config: DataCollectionConfig = Depends(get_data_collection_config),
) -> DeviceService:
    """Get the device service instance."""
    return DeviceService(device_repo, config)


def get_task_service(
    task_repo: TaskRepo = Depends(get_task_repo),
    config: DataCollectionConfig = Depends(get_data_collection_config),
) -> TaskService:
    """Get the task service instance."""
    return TaskService(task_repo, config)


def get_system_service(
    recording_sm: RecordingStateMachine = Depends(get_recording_state_machine),
    workflow_sm: FrankaWorkflowStateMachine = Depends(get_workflow_state_machine),
    episode_repo: EpisodeRepo = Depends(get_raw_episode_repo),
) -> SystemService:
    """Get the system service instance."""
    station_config: StationConfig = load_station_config()
    return SystemService(recording_sm, workflow_sm, episode_repo, station_config)
