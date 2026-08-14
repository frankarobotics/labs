"""Policy contract indexed for extraction: which contract segments each recorded topic feeds."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pipeline_configs import CameraSegment, PolicyContract, PolicySegment


@dataclass(frozen=True)
class PolicyManifest:
    """Recorded topics mapped to the contract segments they feed; everything downstream is keyed by policy_key."""

    contract: PolicyContract
    cameras_by_topic: dict[str, tuple[CameraSegment, ...]]
    state_by_topic: dict[str, tuple[PolicySegment, ...]]
    action_by_topic: dict[str, tuple[PolicySegment, ...]]

    @classmethod
    def from_contract(cls, contract: PolicyContract) -> PolicyManifest:
        """Index a contract by topic; several segments may read one topic (e.g. position and velocity)."""
        return cls(
            contract=contract,
            cameras_by_topic=_group_by_topic(contract.cameras, lambda camera: camera.dataset_topic),
            state_by_topic=_group_by_topic(contract.state, lambda segment: segment.topic),
            action_by_topic=_group_by_topic(contract.action, lambda segment: segment.topic),
        )

    @property
    def camera_keys(self) -> tuple[str, ...]:
        """Camera policy keys in contract order."""
        return tuple(camera.policy_key for camera in self.contract.cameras)

    @property
    def state_keys(self) -> tuple[str, ...]:
        """State policy keys in flat-vector order."""
        return tuple(segment.policy_key for segment in self.contract.state)

    @property
    def action_keys(self) -> tuple[str, ...]:
        """Action policy keys in flat-vector order."""
        return tuple(segment.policy_key for segment in self.contract.action)

    def camera_for(self, policy_key: str) -> CameraSegment:
        """Camera segment a policy key names."""
        for camera in self.contract.cameras:
            if camera.policy_key == policy_key:
                return camera
        raise KeyError(f"no camera declares policy_key {policy_key!r}")

    def order_cameras[Value](self, values_by_key: dict[str, Value]) -> dict[str, Value]:
        """Reorder camera-keyed values into contract order."""
        return _ordered(values_by_key, self.camera_keys)

    def order_state[Value](self, values_by_key: dict[str, Value]) -> dict[str, Value]:
        """Reorder state-keyed values into flat-vector order."""
        return _ordered(values_by_key, self.state_keys)

    def order_action[Value](self, values_by_key: dict[str, Value]) -> dict[str, Value]:
        """Reorder action-keyed values into flat-vector order."""
        return _ordered(values_by_key, self.action_keys)


def load_policy_manifest(contract_path: Path) -> PolicyManifest:
    """Load a policy contract and index it for extraction."""
    if not contract_path.exists():
        raise FileNotFoundError(f"Policy contract not found: {contract_path}")
    return PolicyManifest.from_contract(PolicyContract.from_yaml(contract_path))


def _group_by_topic[Segment: (CameraSegment, PolicySegment)](
    segments: Sequence[Segment], topic_of: Callable[[Segment], str]
) -> dict[str, tuple[Segment, ...]]:
    grouped: defaultdict[str, list[Segment]] = defaultdict(list)
    for segment in segments:
        grouped[topic_of(segment)].append(segment)
    return {topic: tuple(items) for topic, items in grouped.items()}


def _ordered[Value](values_by_key: dict[str, Value], keys: tuple[str, ...]) -> dict[str, Value]:
    return {key: values_by_key[key] for key in keys if key in values_by_key}
