"""Explicit mission state transitions."""

from __future__ import annotations

from .models import MissionState


ALLOWED_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    MissionState.PLANNED: {MissionState.QUEUED, MissionState.CANCELLED},
    MissionState.QUEUED: {MissionState.STARTING, MissionState.CANCELLED, MissionState.ESCALATED},
    MissionState.STARTING: {MissionState.RUNNING, MissionState.FAILED, MissionState.CANCELLED, MissionState.ESCALATED},
    MissionState.RUNNING: {
        MissionState.VERIFYING,
        MissionState.STALLED,
        MissionState.FAILED,
        MissionState.CANCELLED,
        MissionState.ESCALATED,
    },
    MissionState.VERIFYING: {MissionState.COMPLETE, MissionState.FAILED, MissionState.ESCALATED},
    MissionState.FAILED: {MissionState.RETRYING, MissionState.ESCALATED, MissionState.CANCELLED},
    MissionState.STALLED: {MissionState.RETRYING, MissionState.ESCALATED, MissionState.CANCELLED},
    MissionState.RETRYING: {MissionState.STARTING, MissionState.ESCALATED, MissionState.CANCELLED},
    MissionState.ESCALATED: {MissionState.QUEUED, MissionState.CANCELLED},
    MissionState.COMPLETE: set(),
    MissionState.CANCELLED: set(),
}


def can_transition(previous: MissionState | str, new: MissionState | str) -> bool:
    previous_state = MissionState(previous)
    new_state = MissionState(new)
    return previous_state == new_state or new_state in ALLOWED_TRANSITIONS[previous_state]


def transition(previous: MissionState | str, new: MissionState | str) -> MissionState:
    """Validate and return a new state; callers record the event separately."""

    previous_state = MissionState(previous)
    new_state = MissionState(new)
    if not can_transition(previous_state, new_state):
        raise ValueError(f"invalid mission transition: {previous_state.value} -> {new_state.value}")
    return new_state

