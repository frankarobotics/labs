"""LeRobot feature naming conventions dataset-builder owns."""


def get_observation_state_feature_name(policy_key: str) -> str:
    """Generate the LeRobot feature name for one state segment.

    Args:
        policy_key: The state segment's policy key.

    Returns:
        The feature name string for the observation state.
    """
    return f"observation.state.{policy_key}"


def get_annotation_feature_name(policy_key: str) -> str:
    """Generate the LeRobot feature name for one annotation column.

    Args:
        policy_key: The annotation's policy key.

    Returns:
        The feature name string for the annotation column.
    """
    return f"annotation.{policy_key}"
