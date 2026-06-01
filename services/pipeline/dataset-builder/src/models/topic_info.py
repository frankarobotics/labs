from pydantic import BaseModel


class TopicInfo(BaseModel):
    """Represents metadata information for a ROS topic.

    Attributes:
        schema_name (str): Name of the topic schema.
        encoding (str): Encoding type for the topic.
        message_encoding (str): Encoding type for messages.
        message_count (int): Number of messages in the topic.
    """

    schema_name: str
    encoding: str
    message_encoding: str
    message_count: int
