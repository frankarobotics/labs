"""The Nomadic MCAP signal message used for converted LABS measurements."""

from typing import Any, cast

from google.protobuf import (  # type: ignore[import-untyped]
    descriptor_pb2,
    descriptor_pool,
    message_factory,
    timestamp_pb2,
)


def signal_type() -> type[Any]:
    """Build the public nomadic.Signal schema without requiring a protoc executable."""
    definition = descriptor_pb2.FileDescriptorProto(
        name="nomadic_signal.proto",
        package="nomadic",
        syntax="proto3",
        dependency=["google/protobuf/timestamp.proto"],
    )
    vector = definition.message_type.add(name="Vector")
    vector.field.add(name="values", number=1, type=1, label=3)
    signal = definition.message_type.add(name="Signal")
    signal.oneof_decl.add(name="value")
    signal.field.add(name="timestamp", number=1, type=11, type_name=".google.protobuf.Timestamp")
    for name, number, kind in (("number", 2, 1), ("flag", 3, 8), ("text", 4, 9)):
        signal.field.add(name=name, number=number, type=kind, oneof_index=0)
    signal.field.add(name="vector", number=5, type=11, type_name=".nomadic.Vector", oneof_index=0)
    pool = descriptor_pool.DescriptorPool()
    pool.AddSerializedFile(timestamp_pb2.DESCRIPTOR.serialized_pb)
    pool.Add(definition)
    return cast(type[Any], message_factory.GetMessageClass(pool.FindMessageTypeByName("nomadic.Signal")))
