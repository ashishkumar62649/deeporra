"""Tests for IndexStateMachine — pure state transitions, no I/O."""

import pytest

from fcode.contracts.enums import IndexPhase, IndexState
from fcode.indexing.state_machine import (
    IndexStateMachine,
    InvalidIndexStateTransition,
)


# ── Initial state ────────────────────────────────────────────────────────────


class TestInitialState:
    def test_starts_pending(self):
        m = IndexStateMachine()
        assert m.state == IndexState.PENDING

    def test_initial_phase_is_none(self):
        m = IndexStateMachine()
        assert m.phase is None

    def test_initial_completed_phase_is_none(self):
        m = IndexStateMachine()
        assert m.completed_phase is None

    def test_initial_history_contains_pending(self):
        m = IndexStateMachine()
        assert m.history == (IndexState.PENDING,)

    def test_initial_terminal_flag_false(self):
        m = IndexStateMachine()
        assert not m.is_terminal

    def test_initial_replacement_false(self):
        m = IndexStateMachine()
        assert not m.persistent_replacement_started


# ── Happy path ───────────────────────────────────────────────────────────────


class TestHappyPath:
    def _run(self, states):
        m = IndexStateMachine()
        for s in states:
            m.transition(s)
        return m

    def test_complete_legal_sequence(self):
        m = self._run([
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
            IndexState.EMBEDDING,
            IndexState.GRAPHING,
            IndexState.STORING,
            IndexState.COMPLETE,
        ])
        assert m.state == IndexState.COMPLETE

    def test_exact_phase_at_every_state(self):
        m = IndexStateMachine()
        assert m.phase is None  # PENDING
        m.transition(IndexState.SCANNING)
        assert m.phase == IndexPhase.SCAN
        m.transition(IndexState.PARSING)
        assert m.phase == IndexPhase.PARSE
        m.transition(IndexState.CHUNKING)
        assert m.phase == IndexPhase.CHUNK
        m.transition(IndexState.EMBEDDING)
        assert m.phase == IndexPhase.EMBED
        m.transition(IndexState.GRAPHING)
        assert m.phase == IndexPhase.GRAPH
        m.transition(IndexState.STORING)
        assert m.phase == IndexPhase.PERSIST
        m.transition(IndexState.COMPLETE)
        assert m.phase == IndexPhase.PERSIST

    def test_exact_completed_phase_at_every_state(self):
        m = IndexStateMachine()
        assert m.completed_phase is None  # PENDING
        m.transition(IndexState.SCANNING)
        assert m.completed_phase is None
        m.transition(IndexState.PARSING)
        assert m.completed_phase == IndexPhase.SCAN
        m.transition(IndexState.CHUNKING)
        assert m.completed_phase == IndexPhase.PARSE
        m.transition(IndexState.EMBEDDING)
        assert m.completed_phase == IndexPhase.CHUNK
        m.transition(IndexState.GRAPHING)
        assert m.completed_phase == IndexPhase.EMBED
        m.transition(IndexState.STORING)
        assert m.completed_phase == IndexPhase.GRAPH
        m.transition(IndexState.COMPLETE)
        assert m.completed_phase == IndexPhase.PERSIST

    def test_exact_history_after_complete(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING,
                  IndexState.COMPLETE]:
            m.transition(s)
        assert m.history == (
            IndexState.PENDING,
            IndexState.SCANNING,
            IndexState.PARSING,
            IndexState.CHUNKING,
            IndexState.EMBEDDING,
            IndexState.GRAPHING,
            IndexState.STORING,
            IndexState.COMPLETE,
        )

    def test_terminal_true_at_complete(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.transition(IndexState.PARSING)
        m.transition(IndexState.CHUNKING)
        m.transition(IndexState.EMBEDDING)
        m.transition(IndexState.GRAPHING)
        m.transition(IndexState.STORING)
        m.transition(IndexState.COMPLETE)
        assert m.is_terminal

    def test_replacement_flag_becomes_true_only_at_storing(self):
        m = IndexStateMachine()
        assert not m.persistent_replacement_started
        m.transition(IndexState.SCANNING)
        assert not m.persistent_replacement_started
        m.transition(IndexState.PARSING)
        assert not m.persistent_replacement_started
        m.transition(IndexState.CHUNKING)
        assert not m.persistent_replacement_started
        m.transition(IndexState.EMBEDDING)
        assert not m.persistent_replacement_started
        m.transition(IndexState.GRAPHING)
        assert not m.persistent_replacement_started
        m.transition(IndexState.STORING)
        assert m.persistent_replacement_started

    def test_replacement_flag_remains_true_at_complete(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING]:
            m.transition(s)
        assert m.persistent_replacement_started
        m.transition(IndexState.COMPLETE)
        assert m.persistent_replacement_started


# ── Failure transitions ──────────────────────────────────────────────────────


class TestFailureTransitions:
    def test_pending_to_error(self):
        m = IndexStateMachine()
        m.fail()
        assert m.state == IndexState.ERROR

    def test_scanning_to_error(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_parsing_to_error(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.transition(IndexState.PARSING)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_chunking_to_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING]:
            m.transition(s)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_embedding_to_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING]:
            m.transition(s)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_graphing_to_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING]:
            m.transition(s)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_storing_to_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING]:
            m.transition(s)
        m.fail()
        assert m.state == IndexState.ERROR

    def test_active_phase_preserved_on_pending_error(self):
        m = IndexStateMachine()
        m.fail()
        assert m.phase is None

    def test_active_phase_preserved_on_scanning_error(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.fail()
        assert m.phase == IndexPhase.SCAN

    def test_active_phase_preserved_on_parsing_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING]:
            m.transition(s)
        m.fail()
        assert m.phase == IndexPhase.PARSE

    def test_active_phase_preserved_on_chunking_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING]:
            m.transition(s)
        m.fail()
        assert m.phase == IndexPhase.CHUNK

    def test_active_phase_preserved_on_embedding_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING]:
            m.transition(s)
        m.fail()
        assert m.phase == IndexPhase.EMBED

    def test_active_phase_preserved_on_graphing_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING]:
            m.transition(s)
        m.fail()
        assert m.phase == IndexPhase.GRAPH

    def test_active_phase_preserved_on_storing_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING]:
            m.transition(s)
        m.fail()
        assert m.phase == IndexPhase.PERSIST

    def test_completed_phase_preserved_on_pending_error(self):
        m = IndexStateMachine()
        m.fail()
        assert m.completed_phase is None

    def test_completed_phase_preserved_on_scanning_error(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.fail()
        assert m.completed_phase is None

    def test_completed_phase_preserved_on_parsing_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING]:
            m.transition(s)
        m.fail()
        assert m.completed_phase == IndexPhase.SCAN

    def test_completed_phase_preserved_on_chunking_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING]:
            m.transition(s)
        m.fail()
        assert m.completed_phase == IndexPhase.PARSE

    def test_completed_phase_preserved_on_storing_error(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING]:
            m.transition(s)
        m.fail()
        assert m.completed_phase == IndexPhase.GRAPH

    def test_replacement_flag_false_for_pre_storing_failures(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING]:
            m.transition(s)
        m.fail()
        assert not m.persistent_replacement_started

    def test_replacement_flag_true_for_storing_failure(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING]:
            m.transition(s)
        m.fail()
        assert m.persistent_replacement_started

    def test_error_is_terminal(self):
        m = IndexStateMachine()
        m.fail()
        assert m.is_terminal


# ── Illegal transitions ──────────────────────────────────────────────────────


class TestIllegalTransitions:
    def test_pending_to_parsing_rejected(self):
        m = IndexStateMachine()
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.PARSING)

    def test_pending_to_complete_rejected(self):
        m = IndexStateMachine()
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.COMPLETE)

    def test_scanning_to_chunking_rejected(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.CHUNKING)

    def test_backward_transition_rejected(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        m.transition(IndexState.PARSING)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.SCANNING)

    def test_same_state_transition_rejected(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.SCANNING)

    def test_transition_to_pending_rejected(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.PENDING)

    def test_complete_to_error_rejected(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING,
                  IndexState.COMPLETE]:
            m.transition(s)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.ERROR)

    def test_complete_to_scanning_rejected(self):
        m = IndexStateMachine()
        for s in [IndexState.SCANNING, IndexState.PARSING, IndexState.CHUNKING,
                  IndexState.EMBEDDING, IndexState.GRAPHING, IndexState.STORING,
                  IndexState.COMPLETE]:
            m.transition(s)
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.SCANNING)

    def test_error_to_scanning_rejected(self):
        m = IndexStateMachine()
        m.fail()
        with pytest.raises(InvalidIndexStateTransition):
            m.transition(IndexState.SCANNING)

    def test_repeated_fail_rejected(self):
        m = IndexStateMachine()
        m.fail()
        with pytest.raises(InvalidIndexStateTransition):
            m.fail()

    def test_invalid_transition_does_not_mutate_state(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        before = m.state
        try:
            m.transition(IndexState.CHUNKING)
        except InvalidIndexStateTransition:
            pass
        assert m.state == before

    def test_invalid_transition_does_not_mutate_phase(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        before = m.phase
        try:
            m.transition(IndexState.PENDING)
        except InvalidIndexStateTransition:
            pass
        assert m.phase == before

    def test_invalid_transition_does_not_mutate_completed_phase(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        before = m.completed_phase
        try:
            m.transition(IndexState.CHUNKING)
        except InvalidIndexStateTransition:
            pass
        assert m.completed_phase == before

    def test_invalid_transition_does_not_mutate_history(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        before = m.history
        try:
            m.transition(IndexState.PENDING)
        except InvalidIndexStateTransition:
            pass
        assert m.history == before

    def test_invalid_transition_does_not_mutate_replacement_flag(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        before = m.persistent_replacement_started
        try:
            m.transition(IndexState.COMPLETE)
        except InvalidIndexStateTransition:
            pass
        assert m.persistent_replacement_started == before


# ── Public methods ───────────────────────────────────────────────────────────


class TestPublicMethods:
    def test_can_transition_true_for_legal_next(self):
        m = IndexStateMachine()
        assert m.can_transition(IndexState.SCANNING)

    def test_can_transition_true_for_error_from_active(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        assert m.can_transition(IndexState.ERROR)

    def test_can_transition_false_for_illegal_state(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        assert not m.can_transition(IndexState.COMPLETE)
        assert not m.can_transition(IndexState.CHUNKING)
        assert not m.can_transition(IndexState.PENDING)

    def test_can_transition_performs_no_mutation(self):
        m = IndexStateMachine()
        _ = m.can_transition(IndexState.PARSING)
        assert m.state == IndexState.PENDING
        assert m.history == (IndexState.PENDING,)

    def test_can_transition_false_for_string_input(self):
        m = IndexStateMachine()
        assert not m.can_transition("scanning")  # type: ignore

    def test_transition_raises_type_error_for_string_input(self):
        m = IndexStateMachine()
        with pytest.raises(TypeError):
            m.transition("scanning")  # type: ignore

    def test_transition_returns_new_state(self):
        m = IndexStateMachine()
        result = m.transition(IndexState.SCANNING)
        assert result == IndexState.SCANNING

    def test_fail_returns_error(self):
        m = IndexStateMachine()
        result = m.fail()
        assert result == IndexState.ERROR

    def test_history_is_a_tuple(self):
        m = IndexStateMachine()
        assert isinstance(m.history, tuple)

    def test_external_history_operations_cannot_mutate_machine(self):
        m = IndexStateMachine()
        h = m.history
        try:
            h += (IndexState.SCANNING,)  # tuples are immutable
        except TypeError:
            pass
        assert m.history == (IndexState.PENDING,)


# ── Exception ────────────────────────────────────────────────────────────────


class TestInvalidIndexStateTransition:
    def test_exception_stores_current_state(self):
        m = IndexStateMachine()
        m.transition(IndexState.SCANNING)
        try:
            m.transition(IndexState.CHUNKING)
        except InvalidIndexStateTransition as e:
            assert e.current_state == IndexState.SCANNING

    def test_exception_stores_requested_state(self):
        m = IndexStateMachine()
        try:
            m.transition(IndexState.COMPLETE)
        except InvalidIndexStateTransition as e:
            assert e.requested_state == IndexState.COMPLETE

    def test_exception_message_uses_enum_values(self):
        m = IndexStateMachine()
        try:
            m.transition(IndexState.COMPLETE)
        except InvalidIndexStateTransition as e:
            assert "pending" in str(e)
            assert "complete" in str(e)

    def test_exception_message_contains_no_object_repr(self):
        m = IndexStateMachine()
        try:
            m.transition(IndexState.COMPLETE)
        except InvalidIndexStateTransition as e:
            msg = str(e)
            assert "<" not in msg
            assert "object at" not in msg
