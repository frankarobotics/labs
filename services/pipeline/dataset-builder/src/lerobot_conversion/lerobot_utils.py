"""LeRobot feature naming conventions."""


def get_safe_name(value: str) -> str:
    """Sanitize a name for use as a filename, directory or JSON key.

    Removes the leading slash and replaces slashes and dots with underscores.

    Args:
        value: A policy key or ROS topic name.

    Returns:
        A sanitized name safe for use as a filename or json key.
    """
    return value.lstrip("/").replace("/", "_").replace(".", "_")


def get_video_feature_name(policy_key: str) -> str:
    """Generate the LeRobot feature name for a camera.

    Args:
        policy_key: The camera's policy key.

    Returns:
        The feature name string for the video observation.
    """
    return f"observation.images.{get_safe_name(policy_key)}"


def get_observation_state_feature_name(policy_key: str) -> str:
    """Generate the LeRobot feature name for one state segment.

    Args:
        policy_key: The state segment's policy key.

    Returns:
        The feature name string for the observation state.
    """
    return f"observation.state.{get_safe_name(policy_key)}"


def get_annotation_feature_name(policy_key: str) -> str:
    """Generate the LeRobot feature name for one annotation column.

    Args:
        policy_key: The annotation's policy key.

    Returns:
        The feature name string for the annotation column.
    """
    return f"annotation.{policy_key}"
