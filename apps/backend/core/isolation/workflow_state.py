"""
Runtime state management for Docker workflow steps.

Separates static workflow configuration (WorkflowStep) from runtime execution state.
This enables clean state tracking without coupling to the logging system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .workflow_config import WorkflowStep


class StepStatus(Enum):
    """Status of a workflow step during execution."""
    PENDING = "pending"       # Not yet started
    ACTIVE = "active"         # Currently executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Failed (no retry available)
    SKIPPED = "skipped"       # Skipped (already completed)


@dataclass
class WorkflowStepState:
    """
    Runtime state for a single workflow step.

    Wraps the static WorkflowStep configuration with execution state.
    This allows the pipeline to track progress independent of the logging system.
    """

    # Static configuration
    config: WorkflowStep

    # Runtime state
    status: StepStatus = StepStatus.PENDING
    iteration: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    # Execution metadata
    container_id: Optional[str] = None
    commit_sha: Optional[str] = None

    def start(self, iteration: int = 1) -> None:
        """Mark step as started."""
        self.status = StepStatus.ACTIVE
        self.iteration = iteration
        self.started_at = datetime.now()

    def complete(self, commit_sha: Optional[str] = None) -> None:
        """Mark step as successfully completed."""
        self.status = StepStatus.COMPLETED
        self.completed_at = datetime.now()
        if commit_sha:
            self.commit_sha = commit_sha

    def fail(self, error: str) -> None:
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.completed_at = datetime.now()
        self.error = error

    def skip(self) -> None:
        """Mark step as skipped (already completed)."""
        self.status = StepStatus.SKIPPED
        self.completed_at = datetime.now()

    @property
    def is_complete(self) -> bool:
        """Check if step is in a completed state (completed or skipped)."""
        return self.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)

    @property
    def can_retry(self) -> bool:
        """Check if step can be retried (failed and accepts feedback)."""
        return (
            self.status == StepStatus.FAILED
            and self.config.accepts_feedback
        )

    @property
    def name(self) -> str:
        """Convenience accessor for step name."""
        return self.config.name

    @property
    def log_phase(self) -> str:
        """Convenience accessor for log phase."""
        return self.config.log_phase

    @property
    def description(self) -> str:
        """Convenience accessor for description."""
        return self.config.description


def create_workflow_states(workflow_steps: list[WorkflowStep]) -> list[WorkflowStepState]:
    """
    Create runtime state objects for a workflow configuration.

    Args:
        workflow_steps: List of static workflow step configurations

    Returns:
        List of workflow step states with PENDING status
    """
    return [WorkflowStepState(config=step) for step in workflow_steps]


def get_step_by_name(states: list[WorkflowStepState], name: str) -> Optional[WorkflowStepState]:
    """
    Find a workflow step state by name.

    Args:
        states: List of workflow step states
        name: Step name to find

    Returns:
        WorkflowStepState if found, None otherwise
    """
    for state in states:
        if state.name == name:
            return state
    return None


def get_active_step(states: list[WorkflowStepState]) -> Optional[WorkflowStepState]:
    """
    Get the currently active step, if any.

    Args:
        states: List of workflow step states

    Returns:
        The active step, or None if no step is active
    """
    for state in states:
        if state.status == StepStatus.ACTIVE:
            return state
    return None


def get_next_pending_step(states: list[WorkflowStepState]) -> Optional[WorkflowStepState]:
    """
    Get the next pending step in the workflow.

    Args:
        states: List of workflow step states

    Returns:
        The next pending step, or None if all steps are complete/active/failed
    """
    for state in states:
        if state.status == StepStatus.PENDING:
            return state
    return None


def all_steps_complete(states: list[WorkflowStepState]) -> bool:
    """
    Check if all steps are in a completed state.

    Args:
        states: List of workflow step states

    Returns:
        True if all steps are completed or skipped
    """
    return all(state.is_complete for state in states)


def has_failed_steps(states: list[WorkflowStepState]) -> bool:
    """
    Check if any steps have failed.

    Args:
        states: List of workflow step states

    Returns:
        True if any step has failed
    """
    return any(state.status == StepStatus.FAILED for state in states)
