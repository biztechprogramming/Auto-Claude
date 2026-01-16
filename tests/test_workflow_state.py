"""
Tests for workflow_state module.

Tests runtime state management for Docker workflow steps.
"""

import pytest
from datetime import datetime
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


@pytest.fixture
def sample_workflow_configs():
    """Create a sample workflow configuration."""
    return [
        WorkflowStep(
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
        ),
        WorkflowStep(
            name="code_review",
            role=ContainerRole.EVALUATOR,
            log_phase="validation",
            port=8002,
            description="Review code quality",
            prompt_file="qa_reviewer.md",
            skip_if_complete=True,
            accepts_feedback=False,
            kanban_status="ai_review",
            task_template="Review code quality for {spec_name}"
        ),
        WorkflowStep(
            name="testing",
            role=ContainerRole.QA,
            log_phase="testing",
            port=8003,
            description="Run automated tests",
            prompt_file="qa_reviewer.md",
            skip_if_complete=True,
            accepts_feedback=False,
            kanban_status="ai_testing",
            task_template="Run automated tests for {spec_name}"
        ),
    ]


class TestWorkflowStepState:
    """Test WorkflowStepState class."""

    def test_initial_state(self, sample_step_config):
        """Test initial state of WorkflowStepState."""
        state = WorkflowStepState(config=sample_step_config)

        assert state.status == StepStatus.PENDING
        assert state.iteration == 0
        assert state.started_at is None
        assert state.completed_at is None
        assert state.error is None
        assert state.container_id is None
        assert state.commit_sha is None

    def test_start_method(self, sample_step_config):
        """Test starting a step."""
        state = WorkflowStepState(config=sample_step_config)

        before_time = datetime.now()
        state.start(iteration=1)
        after_time = datetime.now()

        assert state.status == StepStatus.ACTIVE
        assert state.iteration == 1
        assert state.started_at is not None
        assert before_time <= state.started_at <= after_time

    def test_complete_method(self, sample_step_config):
        """Test completing a step."""
        state = WorkflowStepState(config=sample_step_config)
        state.start()

        before_time = datetime.now()
        state.complete(commit_sha="abc123")
        after_time = datetime.now()

        assert state.status == StepStatus.COMPLETED
        assert state.completed_at is not None
        assert before_time <= state.completed_at <= after_time
        assert state.commit_sha == "abc123"

    def test_fail_method(self, sample_step_config):
        """Test failing a step."""
        state = WorkflowStepState(config=sample_step_config)
        state.start()

        before_time = datetime.now()
        state.fail("Error message")
        after_time = datetime.now()

        assert state.status == StepStatus.FAILED
        assert state.completed_at is not None
        assert before_time <= state.completed_at <= after_time
        assert state.error == "Error message"

    def test_skip_method(self, sample_step_config):
        """Test skipping a step."""
        state = WorkflowStepState(config=sample_step_config)

        before_time = datetime.now()
        state.skip()
        after_time = datetime.now()

        assert state.status == StepStatus.SKIPPED
        assert state.completed_at is not None
        assert before_time <= state.completed_at <= after_time

    def test_is_complete_property(self, sample_step_config):
        """Test is_complete property."""
        state = WorkflowStepState(config=sample_step_config)

        # Pending/Active/Failed are not complete
        assert state.is_complete is False
        state.start()
        assert state.is_complete is False
        state.fail("error")
        assert state.is_complete is False

        # Reset to pending
        state.status = StepStatus.PENDING

        # Completed is complete
        state.complete()
        assert state.is_complete is True

        # Reset to pending
        state.status = StepStatus.PENDING

        # Skipped is complete
        state.skip()
        assert state.is_complete is True

    def test_can_retry_property(self, sample_step_config):
        """Test can_retry property."""
        state = WorkflowStepState(config=sample_step_config)

        # Can't retry if not failed
        assert state.can_retry is False
        state.start()
        assert state.can_retry is False
        state.complete()
        assert state.can_retry is False

        # Can retry if failed and accepts_feedback
        state.status = StepStatus.FAILED
        assert state.can_retry is True

    def test_can_retry_no_feedback(self):
        """Test can_retry when step doesn't accept feedback."""
        config = WorkflowStep(
            name="testing",
            role=ContainerRole.QA,
            log_phase="testing",
            port=8003,
            description="Run tests",
            prompt_file="test.md",
            accepts_feedback=False,  # No feedback
        )
        state = WorkflowStepState(config=config)
        state.fail("error")

        assert state.can_retry is False

    def test_convenience_properties(self, sample_step_config):
        """Test convenience accessor properties."""
        state = WorkflowStepState(config=sample_step_config)

        assert state.name == "coding"
        assert state.log_phase == "coding"
        assert state.description == "Implement code changes"


class TestCreateWorkflowStates:
    """Test create_workflow_states function."""

    def test_creates_states_from_configs(self, sample_workflow_configs):
        """Test creating workflow states from configs."""
        states = create_workflow_states(sample_workflow_configs)

        assert len(states) == 3
        assert all(isinstance(s, WorkflowStepState) for s in states)
        assert all(s.status == StepStatus.PENDING for s in states)

        assert states[0].name == "coding"
        assert states[1].name == "code_review"
        assert states[2].name == "testing"

    def test_creates_empty_list(self):
        """Test creating workflow states from empty config."""
        states = create_workflow_states([])
        assert states == []


class TestGetStepByName:
    """Test get_step_by_name function."""

    def test_finds_step_by_name(self, sample_workflow_configs):
        """Test finding a step by name."""
        states = create_workflow_states(sample_workflow_configs)

        step = get_step_by_name(states, "code_review")
        assert step is not None
        assert step.name == "code_review"
        assert step.log_phase == "validation"

    def test_returns_none_when_not_found(self, sample_workflow_configs):
        """Test returning None when step not found."""
        states = create_workflow_states(sample_workflow_configs)

        step = get_step_by_name(states, "nonexistent")
        assert step is None


class TestGetActiveStep:
    """Test get_active_step function."""

    def test_finds_active_step(self, sample_workflow_configs):
        """Test finding the active step."""
        states = create_workflow_states(sample_workflow_configs)
        states[1].start()

        active = get_active_step(states)
        assert active is not None
        assert active.name == "code_review"
        assert active.status == StepStatus.ACTIVE

    def test_returns_none_when_no_active_step(self, sample_workflow_configs):
        """Test returning None when no step is active."""
        states = create_workflow_states(sample_workflow_configs)

        active = get_active_step(states)
        assert active is None


class TestGetNextPendingStep:
    """Test get_next_pending_step function."""

    def test_finds_next_pending_step(self, sample_workflow_configs):
        """Test finding the next pending step."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].start()

        next_step = get_next_pending_step(states)
        assert next_step is not None
        assert next_step.name == "testing"

    def test_returns_first_pending(self, sample_workflow_configs):
        """Test returning first pending step."""
        states = create_workflow_states(sample_workflow_configs)

        next_step = get_next_pending_step(states)
        assert next_step is not None
        assert next_step.name == "coding"

    def test_returns_none_when_no_pending(self, sample_workflow_configs):
        """Test returning None when no pending steps."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].complete()
        states[2].complete()

        next_step = get_next_pending_step(states)
        assert next_step is None


class TestAllStepsComplete:
    """Test all_steps_complete function."""

    def test_returns_true_when_all_complete(self, sample_workflow_configs):
        """Test returning True when all steps are complete."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].skip()
        states[2].complete()

        assert all_steps_complete(states) is True

    def test_returns_false_when_some_pending(self, sample_workflow_configs):
        """Test returning False when some steps are pending."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        # states[1] is still pending

        assert all_steps_complete(states) is False

    def test_returns_false_when_some_active(self, sample_workflow_configs):
        """Test returning False when some steps are active."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].start()

        assert all_steps_complete(states) is False

    def test_returns_false_when_some_failed(self, sample_workflow_configs):
        """Test returning False when some steps failed."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].fail("error")

        assert all_steps_complete(states) is False


class TestHasFailedSteps:
    """Test has_failed_steps function."""

    def test_returns_true_when_has_failed(self, sample_workflow_configs):
        """Test returning True when there are failed steps."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].fail("error")

        assert has_failed_steps(states) is True

    def test_returns_false_when_no_failed(self, sample_workflow_configs):
        """Test returning False when no failed steps."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].start()

        assert has_failed_steps(states) is False

    def test_returns_false_when_all_complete(self, sample_workflow_configs):
        """Test returning False when all steps complete."""
        states = create_workflow_states(sample_workflow_configs)
        states[0].complete()
        states[1].complete()
        states[2].skip()

        assert has_failed_steps(states) is False
