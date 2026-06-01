from models.observation import Observation


def get_safe_topic_name(topic: str) -> str:
    """Convert a ROS topic name to a safe string.

    Removes the leading slash and replaces slashes and dots with underscores.

    Args:
        topic: The original ROS topic name as a string.

    Returns:
        A sanitized topic name string safe for use as a filename or json key.
    """
    return topic.lstrip("/").replace("/", "_").replace(".", "_")


def get_video_feature_name(topic: str) -> str:
    """Generate the feature name for a video observation given a ROS topic.

    Args:
        topic: The ROS topic name as a string.

    Returns:
        The feature name string for the video observation.
    """
    return f"observation.images.{get_safe_topic_name(topic)}"


def get_observation_state_feature_name(topic: str) -> str:
    """Generate the feature name for an observation state given a ROS topic.

    Args:
        topic: The ROS topic name as a string.

    Returns:
        The feature name string for the observation state.
    """
    return f"observation.state.{get_safe_topic_name(topic)}"


def get_observation_names(sample_observation: Observation) -> dict[str, list[str]]:
    """Extract observation state names for each topic from a sample Observation.

    Args:
        sample_observation: An Observation object containing state information.

    Returns:
        A dictionary mapping each topic to a list of its state names.
    """
    observation_names: dict[str, list[str]] = {}
    for topic, state in sample_observation.state.items():
        observation_names[topic] = state.names.copy()
    return observation_names


def get_action_names(sample_observation: Observation) -> list[str]:
    """Generate a list of action feature names from a sample Observation.

    Args:
        sample_observation: An Observation object containing action information.

    Returns:
        A list of action feature names in the format 'topic_name_action_name'.
    """
    action_names: list[str] = []
    for topic, action in sample_observation.action.items():
        for name in action.names:
            action_names.append(f"{get_safe_topic_name(topic)}_{name}")

    return action_names
