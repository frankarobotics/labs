from pydantic import BaseModel


class ObservationState(BaseModel):
    """Represents the robot state of an observation at a specific timestamp.

    Attributes:
        timestamp_ns (int): Timestamp in epoch nanoseconds.
        values (list[float]): List of values (joint positions, orientation, etc).
        names (list[str]): List of names corresponding to values.
    """

    timestamp_ns: int
    values: list[float]
    names: list[str]
