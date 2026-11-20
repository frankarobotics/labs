import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from loguru import logger
from pipeline_configs import PolicyContract

from lerobot_conversion.policy_manifest import PolicyManifest

DEPLOYMENT_CONTRACT = Path(__file__).parents[4] / "deployments/fr3_duo_example/config_contract_gr00t.yml"

# two state segments share /arm/joint_states, which is what makes a topic-keyed layout impossible
CONTRACT_DATA: dict[str, Any] = {
    "version": 1,
    "policy": {"control_rate_hz": 20, "dtype": "float32"},
    "cameras": [
        {"policy_key": "head", "topic": "/head/zed_node/rgb/image_rect_color", "shape": [480, 640, 3], "resize": True},
        {"policy_key": "wrist", "topic": "/wrist/camera/color/image_raw", "shape": [480, 640, 3], "resize": False},
    ],
    "state": [
        {
            "policy_key": "arm_position",
            "topic": "/arm/joint_states",
            "message_type": "sensor_msgs/JointState",
            "field": "position",
            "element_names": ["joint1", "joint2"],
        },
        {
            "policy_key": "arm_velocity",
            "topic": "/arm/joint_states",
            "message_type": "sensor_msgs/JointState",
            "field": "velocity",
            "element_names": ["joint1", "joint2"],
        },
        {
            "policy_key": "arm_wrench",
            "topic": "/arm/external_wrench",
            "message_type": "geometry_msgs/WrenchStamped",
        },
    ],
    "action": [
        {
            "policy_key": "arm",
            "topic": "/follower/joint_states",
            "message_type": "sensor_msgs/JointState",
            "field": "position",
            "element_names": ["joint1", "joint2"],
        },
        {"policy_key": "gripper", "topic": "/follower/gripper/target", "message_type": "std_msgs/Float32"},
    ],
    "annotations": [
        {"policy_key": "human.action.task_description", "original_key": "task_index"},
        {"policy_key": "human.validity"},
    ],
}


@pytest.fixture
def warnings_log() -> Iterator[list[str]]:
    """Warnings emitted during the test; loguru bypasses the stdlib logging caplog hooks into."""
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]), level="WARNING")
    yield messages
    logger.remove(sink_id)


@pytest.fixture(scope="session")
def contract_data() -> dict[str, Any]:
    return copy.deepcopy(CONTRACT_DATA)


@pytest.fixture
def contract() -> PolicyContract:
    return PolicyContract.model_validate(CONTRACT_DATA)


@pytest.fixture
def manifest(contract: PolicyContract) -> PolicyManifest:
    return PolicyManifest.from_contract(contract)


@pytest.fixture
def deployment_manifest() -> PolicyManifest:
    return PolicyManifest.from_contract(PolicyContract.from_yaml(DEPLOYMENT_CONTRACT))
