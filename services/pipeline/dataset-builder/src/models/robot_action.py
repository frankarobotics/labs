from pydantic import BaseModel


class RobotAction(BaseModel):
    """Represents a single robot action.

    Attributes:
        timestamp_ns (int): The time the action occurred, in epoch nanoseconds.
        publish_time_ns (int): The time the action was published, in epoch nanoseconds.
        values (list[float]): The values associated with the robot action.
        names (list[str]): The names of the action dimensions.
    """

    timestamp_ns: int
    publish_time_ns: int
    values: list[float]
    names: list[str]
