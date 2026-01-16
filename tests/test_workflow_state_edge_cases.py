"""
Edge case and robustness tests for workflow_state module.

Tests scenarios that could cause failures in production but might pass
with simple happy-path testing.
"""

import pytest
from datetime import datetime
from unittest.mock import patch
from apps.backend.core.isolation.workflow_state import (
    StepStatus,
    WorkflowStepState,
    create_workflow_states,
    get_step_by_name,
    get_active_step,
    get_next_pending_step,
    all_steps_complete,
    has_failed_steps,
)
from apps.backend.core.isolation.workflow_config import WorkflowStep
from apps.backend.core.isolation.base import ContainerRole


@pytest.fixture
def sample_step_config():
    """Create a sample WorkflowStep configuration."""
    return WorkflowStep(
        name="coding",
        role=ContainerRole.DEVELOPER,
        log_phase="coding",
        port=8001,
        description="Implement code changes",
        prompt_file="coder.md",
        skip_if_complete=True,
        accepts_feedback=True,
        kanban_status="coding",
        task_template="Implement features for {spec_name}"
    )


class TestStateTransitionInvariants:
    """Test that state transitions maintain invariants."""

    def test_cannot_complete_before_starting(self, sample_step_config):
        """Test completing a step that was never started."""
        state = WorkflowStepState(config=sample_step_config)

        # This is allowed - step can be marked complete without being active
        state.complete()

        assert state.status == StepStatus.COMPLETED
        assert state.started_at is None  # Never started
        assert state.completed_at is not None

    def test_multiple_start_calls(self, sample_step_config):
        """Test calling start() multiple times."""
        state = WorkflowStepState(config=sample_step_config)

        state.start(iteration=1)
        first_start = state.started_at

        # Wait a tiny bit to ensure time difference
        import time
        time.sleep(0.001)

        state.start(iteration=2)
        second_start = state.started_at

        # Second start should update the time
        assert second_start > first_start
        assert state.iteration == 2

    def test_complete_after_complete(self, sample_step_config):
        """Test calling complete() on already completed step."""
        state = WorkflowStepState(config=sample_step_config)

        state.complete(commit_sha="abc123")
        first_completed = state.completed_at

        import time
        time.sleep(0.001)

        # Complete again with different sha
        state.complete(commit_sha="def456")
        second_completed = state.completed_at

        # Should update completed_at and commit_sha
        assert second_completed > first_completed
        assert state.commit_sha == "def456"

    def test_fail_after_complete(self, sample_step_config):
        """Test failing a completed step (regression scenario)."""
        state = WorkflowStepState(config=sample_step_config)

        state.complete(commit_sha="abc123")
        state.fail("Later error found")

        # Failure should overwrite completion
        assert state.status == StepStatus.FAILED
        assert state.error == "Later error found"
        # commit_sha should remain
        assert state.commit_sha == "abc123"

    def test_complete_after_fail(self, sample_step_config):
        """Test completing after failure (retry scenario)."""
        state = WorkflowStepState(config=sample_step_config)

        state.start()
        state.fail("First attempt failed")

        # Retry: start again and complete
        state.start(iteration=2)
        state.complete(commit_sha="xyz789")

        assert state.status == StepStatus.COMPLETED
        assert state.commit_sha == "xyz789"
        # Error should still be there from first attempt
        assert state.error == "First attempt failed"

    def test_skip_after_start(self, sample_step_config):
        """Test skipping an active step."""
        state = WorkflowStepState(config=sample_step_config)

        state.start()
        state.skip()

        assert state.status == StepStatus.SKIPPED
        assert state.started_at is not None  # Was started
        assert state.completed_at is not None  # Now skipped


class TestCanRetryEdgeCases:
    """Test can_retry property edge cases."""

    def test_can_retry_with_none_config(self):
        """Test can_retry when config might be corrupted."""
        # This would be a bug, but we should handle gracefully
        state = WorkflowStepState(config=None)
        state.status = StepStatus.FAILED

        with pytest.raises(AttributeError):
            # Should raise because config is None
            _ = state.can_retry

    def test_can_retry_skipped_step_with_feedback(self, sample_step_config):
        """Test that skipped steps cannot be retried even if they accept feedback."""
        state = WorkflowStepState(config=sample_step_config)
        state.skip()

        # Skipped steps are not failed, so can't retry
        assert state.can_retry is False

    def test_can_retry_active_step(self, sample_step_config):
        """Test that active steps cannot be retried."""
        state = WorkflowStepState(config=sample_step_config)
        state.start()

        assert state.can_retry is False


class TestHelperFunctionsEdgeCases:
    """Test helper functions with edge cases."""

    def test_get_step_by_name_case_sensitive(self, sample_step_config):
        """Test that get_step_by_name is case-sensitive."""
        states = [WorkflowStepState(config=sample_step_config)]

        # Exact match works
        step = get_step_by_name(states, "coding")
        assert step is not None

        # Different case should not match
        step = get_step_by_name(states, "Coding")
        assert step is None

        step = get_step_by_name(states, "CODING")
        assert step is None

    def test_get_step_by_name_empty_string(self, sample_step_config):
        """Test get_step_by_name with empty string."""
        states = [WorkflowStepState(config=sample_step_config)]

        step = get_step_by_name(states, "")
        assert step is None

    def test_get_step_by_name_none(self, sample_step_config):
        """Test get_step_by_name with None (returns None instead of raising)."""
        states = [WorkflowStepState(config=sample_step_config)]

        # Currently returns None instead of raising - this is a potential bug
        # because state.name == None will never match, but doesn't explicitly validate
        step = get_step_by_name(states, None)
        assert step is None  # Current behavior (may want to add validation)

    def test_get_active_step_multiple_active(self, sample_step_config):
        """Test get_active_step when multiple steps are active (invariant violation)."""
        config2 = WorkflowStep(
            name="testing",
            role=ContainerRole.QA,
            log_phase="testing",
            port=8003,
            description="Test",
            prompt_file="test.md",
        )

        state1 = WorkflowStepState(config=sample_step_config)
        state2 = WorkflowStepState(config=config2)

        state1.start()
        state2.start()

        states = [state1, state2]

        # Should return the FIRST active step
        active = get_active_step(states)
        assert active is not None
        assert active.name == "coding"  # First one

    def test_get_active_step_none_input(self):
        """Test get_active_step with None input."""
        with pytest.raises(TypeError):
            get_active_step(None)

    def test_all_steps_complete_empty_list(self):
        """Test all_steps_complete with empty list."""
        # Empty list means all steps are complete (vacuous truth)
        assert all_steps_complete([]) is True

    def test_has_failed_steps_empty_list(self):
        """Test has_failed_steps with empty list."""
        # Empty list means no failed steps
        assert has_failed_steps([]) is False


class TestIsCompleteProperty:
    """Test is_complete property with edge cases."""

    def test_is_complete_after_reset_to_pending(self, sample_step_config):
        """Test is_complete after manually resetting to pending."""
        state = WorkflowStepState(config=sample_step_config)

        state.complete()
        assert state.is_complete is True

        # Manual reset (simulating retry logic)
        state.status = StepStatus.PENDING
        assert state.is_complete is False

    def test_is_complete_consistency(self, sample_step_config):
        """Test that is_complete is consistent across all states."""
        state = WorkflowStepState(config=sample_step_config)

        # PENDING -> not complete
        assert state.status == StepStatus.PENDING
        assert state.is_complete is False

        # ACTIVE -> not complete
        state.start()
        assert state.status == StepStatus.ACTIVE
        assert state.is_complete is False

        # FAILED -> not complete
        state.fail("error")
        assert state.status == StepStatus.FAILED
        assert state.is_complete is False

        # Reset to test completion states
        state.status = StepStatus.PENDING

        # COMPLETED -> complete
        state.complete()
        assert state.status == StepStatus.COMPLETED
        assert state.is_complete is True

        # SKIPPED -> complete
        state.status = StepStatus.PENDING
        state.skip()
        assert state.status == StepStatus.SKIPPED
        assert state.is_complete is True


class TestConvenienceProperties:
    """Test convenience properties handle edge cases."""

    def test_convenience_properties_with_none_config(self):
        """Test convenience properties when config is None."""
        state = WorkflowStepState(config=None)

        with pytest.raises(AttributeError):
            _ = state.name

        with pytest.raises(AttributeError):
            _ = state.log_phase

        with pytest.raises(AttributeError):
            _ = state.description


class TestWorkflowLifecycle:
    """Test complete workflow lifecycle scenarios."""

    def test_happy_path_lifecycle(self, sample_step_config):
        """Test complete happy path lifecycle."""
        state = WorkflowStepState(config=sample_step_config)

        # Start
        assert state.status == StepStatus.PENDING
        state.start(iteration=1)
        assert state.status == StepStatus.ACTIVE
        assert state.iteration == 1

        # Complete
        state.complete(commit_sha="abc123")
        assert state.status == StepStatus.COMPLETED
        assert state.is_complete is True
        assert state.commit_sha == "abc123"

    def test_retry_lifecycle(self, sample_step_config):
        """Test retry lifecycle: fail -> reset -> retry -> complete."""
        state = WorkflowStepState(config=sample_step_config)

        # First attempt
        state.start(iteration=1)
        state.fail("Test failed")
        assert state.can_retry is True

        # Reset for retry (simulating docker_strategy.py lines 414-419)
        state.status = StepStatus.PENDING
        state.started_at = None
        state.completed_at = None
        state.error = None

        # Second attempt
        state.start(iteration=2)
        state.complete(commit_sha="def456")
        assert state.status == StepStatus.COMPLETED
        assert state.iteration == 2

    def test_skip_lifecycle(self, sample_step_config):
        """Test skip lifecycle for already-completed work."""
        state = WorkflowStepState(config=sample_step_config)

        # Directly skip (no start needed)
        state.skip()
        assert state.status == StepStatus.SKIPPED
        assert state.is_complete is True
        assert state.started_at is None  # Never started


class TestDateTimeHandling:
    """Test datetime handling with mocking to avoid flakiness."""

    @patch('apps.backend.core.isolation.workflow_state.datetime')
    def test_start_sets_datetime(self, mock_datetime, sample_step_config):
        """Test that start() sets started_at to current time."""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        state = WorkflowStepState(config=sample_step_config)
        state.start()

        assert state.started_at == fixed_time
        mock_datetime.now.assert_called_once()

    @patch('apps.backend.core.isolation.workflow_state.datetime')
    def test_complete_sets_datetime(self, mock_datetime, sample_step_config):
        """Test that complete() sets completed_at to current time."""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        state = WorkflowStepState(config=sample_step_config)
        state.complete()

        assert state.completed_at == fixed_time
        mock_datetime.now.assert_called_once()

    @patch('apps.backend.core.isolation.workflow_state.datetime')
    def test_fail_sets_datetime(self, mock_datetime, sample_step_config):
        """Test that fail() sets completed_at to current time."""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        state = WorkflowStepState(config=sample_step_config)
        state.fail("error")

        assert state.completed_at == fixed_time
        mock_datetime.now.assert_called_once()

    @patch('apps.backend.core.isolation.workflow_state.datetime')
    def test_skip_sets_datetime(self, mock_datetime, sample_step_config):
        """Test that skip() sets completed_at to current time."""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_datetime.now.return_value = fixed_time

        state = WorkflowStepState(config=sample_step_config)
        state.skip()

        assert state.completed_at == fixed_time
        mock_datetime.now.assert_called_once()
