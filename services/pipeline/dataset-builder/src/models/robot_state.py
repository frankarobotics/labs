from pydantic import BaseModel


class RobotState(BaseModel):
    """Represents the state information for a robotics system.

    Attributes:
        timestamp_ns (int): Timestamp in epoch nanoseconds when the data was recorded.
        publish_time_ns (int): Time in epoch nanoseconds when the data was published.
        values (list[float]): Values of the state information.
        names (list[str]): Names associated with the values.

    """

    timestamp_ns: int
    publish_time_ns: int
    values: list[float]
    names: list[str]
