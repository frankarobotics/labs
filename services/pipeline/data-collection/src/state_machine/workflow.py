from __future__ import annotations

from typing import Any

from loguru import logger
from statemachine import Event, State, StateMachine


class BaseWorkflowStateMachine(StateMachine):
    """Abstract base state machine for the LABS workflow.

    Defines the common states and events for the teleoperation workflow:
    IDLE, READY, SYNCING, and FOLLOWING. Subclasses must implement the
    action methods and service callback registration.

    Note: Abstract methods use ``raise NotImplementedError`` rather than
    ``@abstractmethod`` to avoid a metaclass conflict with ``StateMachineMeta``.
    Thread safety is provided by ``python-statemachine``'s built-in processing
    lock (available since 3.x).
    """

    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        """Initialize the state machine and register service callbacks."""
        super().__init__(**kwargs)
        self._register_service_callbacks()

    def after_transition(self, event: str, source: State, target: State) -> None:
        """Procedure called after every state transition."""
        logger.info(f"State transition: {source.id} -> {target.id} [event: {event}]")

    # States
    idle = State("IDLE", initial=True)
    ready = State("READY")
    syncing = State("SYNCING")
    following = State("FOLLOWING")
    autorecovery = State("AUTORECOVERY")

    # Events
    get_ready = Event(
        idle.to(ready) | following.to(ready) | syncing.to(ready) | autorecovery.to(ready) | ready.to.itself()
    )
    start_syncing = Event(ready.to(syncing) | syncing.to.itself())
    start_following = Event(syncing.to(following) | following.to.itself())
    start_autorecovery = Event(
        following.to(autorecovery) | syncing.to(autorecovery) | ready.to(autorecovery) | autorecovery.to.itself()
    )
    get_idle = Event(ready.to(idle) | syncing.to(idle) | following.to(idle) | autorecovery.to(idle) | idle.to.itself())

    def before_get_ready(self) -> None:
        """Prepare the system to transition to READY state."""
        raise NotImplementedError

    def before_start_syncing(self) -> None:
        """Prepare the system to transition to SYNCING state."""
        raise NotImplementedError

    def before_get_idle(self) -> None:
        """Prepare the system to transition to IDLE state."""
        raise NotImplementedError

    def _register_service_callbacks(self) -> None:
        """Register any external service callbacks. Called at the end of ``__init__``."""
        raise NotImplementedError
