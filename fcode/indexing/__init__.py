"""F Code indexing — state machine and pipeline orchestration.

The index_service.py pipeline orchestrator belongs to later WP5 steps.
"""

from fcode.indexing.state_machine import (
    IndexStateMachine,
    InvalidIndexStateTransition,
)

__all__ = [
    "IndexStateMachine",
    "InvalidIndexStateTransition",
]
