"""Pure state machine for indexing pipeline phases.

This module performs no I/O, imports no feature modules (scanner, parser,
chunker, embeddings, graph, storage, CLI, config, network, filesystem),
and knows nothing about the repository path.

It is a deterministic state controller only.
"""

from typing import Optional

from fcode.contracts.enums import IndexPhase, IndexState


class InvalidIndexStateTransition(ValueError):
    """Raised when an illegal state transition is attempted."""

    def __init__(
        self,
        current_state: IndexState,
        requested_state: IndexState,
    ) -> None:
        self.current_state = current_state
        self.requested_state = requested_state
        super().__init__(
            f"invalid index state transition: {current_state.value} -> {requested_state.value}"
        )


_FORWARD_SEQUENCE: list[IndexState] = [
    IndexState.PENDING,
    IndexState.SCANNING,
    IndexState.PARSING,
    IndexState.CHUNKING,
    IndexState.EMBEDDING,
    IndexState.GRAPHING,
    IndexState.STORING,
    IndexState.COMPLETE,
]

_ACTIVE_PHASE_MAP: dict[IndexState, Optional[IndexPhase]] = {
    IndexState.PENDING: None,
    IndexState.SCANNING: IndexPhase.SCAN,
    IndexState.PARSING: IndexPhase.PARSE,
    IndexState.CHUNKING: IndexPhase.CHUNK,
    IndexState.EMBEDDING: IndexPhase.EMBED,
    IndexState.GRAPHING: IndexPhase.GRAPH,
    IndexState.STORING: IndexPhase.PERSIST,
    IndexState.COMPLETE: IndexPhase.PERSIST,
}

_COMPLETED_PHASE_MAP: dict[IndexState, Optional[IndexPhase]] = {
    IndexState.PENDING: None,
    IndexState.SCANNING: None,
    IndexState.PARSING: IndexPhase.SCAN,
    IndexState.CHUNKING: IndexPhase.PARSE,
    IndexState.EMBEDDING: IndexPhase.CHUNK,
    IndexState.GRAPHING: IndexPhase.EMBED,
    IndexState.STORING: IndexPhase.GRAPH,
    IndexState.COMPLETE: IndexPhase.PERSIST,
}


class IndexStateMachine:
    """Deterministic indexing state machine.

    The machine starts in PENDING with no active phase.
    It follows a strict forward sequence and allows ERROR
    from any non-terminal state.  Once COMPLETE or ERROR is
    reached no further transitions are permitted.

    Phase A (preflight):  PENDING
    Phase B (in memory):  SCANNING … GRAPHING
    Phase C (persistent): STORING, COMPLETE
    """

    def __init__(self) -> None:
        self._state: IndexState = IndexState.PENDING
        self._phase: Optional[IndexPhase] = None
        self._completed_phase: Optional[IndexPhase] = None
        self._history: list[IndexState] = [IndexState.PENDING]
        self._persistent_replacement_started: bool = False

    @property
    def state(self) -> IndexState:
        return self._state

    @property
    def phase(self) -> Optional[IndexPhase]:
        return self._phase

    @property
    def completed_phase(self) -> Optional[IndexPhase]:
        return self._completed_phase

    @property
    def history(self) -> tuple[IndexState, ...]:
        return tuple(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._state in (IndexState.COMPLETE, IndexState.ERROR)

    @property
    def persistent_replacement_started(self) -> bool:
        return self._persistent_replacement_started

    def can_transition(self, next_state: IndexState) -> bool:
        if not isinstance(next_state, IndexState):
            return False
        return self._is_legal_transition(next_state)

    def transition(self, next_state: IndexState) -> IndexState:
        if not isinstance(next_state, IndexState):
            raise TypeError(
                f"expected IndexState, got {type(next_state).__name__}"
            )
        if not self._is_legal_transition(next_state):
            raise InvalidIndexStateTransition(self._state, next_state)

        prev_state = self._state
        prev_phase = self._phase

        self._state = next_state
        self._history.append(next_state)

        if next_state == IndexState.ERROR:
            self._phase = _ACTIVE_PHASE_MAP.get(prev_state, prev_phase)
        else:
            self._phase = _ACTIVE_PHASE_MAP[next_state]
            self._completed_phase = _COMPLETED_PHASE_MAP[next_state]

        if next_state == IndexState.STORING:
            self._persistent_replacement_started = True

        return self._state

    def fail(self) -> IndexState:
        return self.transition(IndexState.ERROR)

    def _is_legal_transition(self, next_state: IndexState) -> bool:
        if self._state in (IndexState.COMPLETE, IndexState.ERROR):
            return False
        if next_state == IndexState.PENDING:
            return False
        if next_state == self._state:
            return False
        if next_state == IndexState.ERROR:
            return True
        try:
            current_idx = _FORWARD_SEQUENCE.index(self._state)
            next_idx = _FORWARD_SEQUENCE.index(next_state)
            return next_idx == current_idx + 1
        except ValueError:
            return False
