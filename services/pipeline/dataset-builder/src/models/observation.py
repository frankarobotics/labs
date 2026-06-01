from pydantic import BaseModel

from models.observation_action import ObservationAction
from models.observation_image import ObservationImage
from models.observation_state import ObservationState


class Observation(BaseModel):
    """Represents a single observation in a data collection episode.

    Attributes:
        timestamp_ns (int): The time the observation was recorded in epoch nanoseconds.
        frame_index (int): The index of the frame in the episode.
        episode_index (int): The index of the episode.
        image (dict[str, ObservationImage]): The image data associated with the observation.
        state (dict[str, ObservationState]): The state information for each key.
        action (dict[str, ObservationAction]): The action information for each key.
    """

    timestamp_ns: int
    frame_index: int
    episode_index: int
    image: dict[str, ObservationImage]
    state: dict[str, ObservationState]
    action: dict[str, ObservationAction]

    class Config:  # noqa: D106
        arbitrary_types_allowed = True
