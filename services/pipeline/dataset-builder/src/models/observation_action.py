from pydantic import BaseModel


class ObservationAction(BaseModel):
    """Represents an action of an observation with a timestamp, values and names.

    Attributes:
        timestamp_ns (int): Timestamp in epoch nanoseconds.
        values (list[float]): The action values.
        names (list[str]): The action names.
    """

    timestamp_ns: int
    values: list[float]
    names: list[str]
