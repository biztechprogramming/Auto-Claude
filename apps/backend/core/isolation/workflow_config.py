"""
Docker Pipeline Workflow Configuration.

Defines the configurable multi-step workflow for Docker isolation.
Each step represents a container in the pipeline with its configuration.
"""

from dataclasses import dataclass
from typing import Optional
from .base import ContainerRole


@dataclass
class WorkflowStep:
    """Configuration for a single step in the Docker workflow."""

    # Unique identifier for this step
    name: str

    # Container role (maps to Docker image)
    role: ContainerRole

    # Log phase this step maps to (for UI display)
    log_phase: str  # 'planning', 'coding', 'validation', 'testing'

    # Port for FastAPI server
    port: int

    # Human-readable description
    description: str

    # Prompt file to use for this step (relative to prompts/ directory)
    prompt_file: str

    # Whether to skip if phase is already completed
    skip_if_complete: bool = True

    # Whether this step can receive feedback from subsequent steps
    accepts_feedback: bool = False

    # Kanban status to show during execution
    kanban_status: str = "in_progress"

    # Task description template (can use {spec_name} placeholder)
    task_template: str = "Process {spec_name}"


# Default Docker Pipeline Workflow
# This is the standard 3-step pipeline: Developer → Evaluator → QA
# Each step uses Docker-specific prompts from prompts/docker/ folder
DEFAULT_WORKFLOW = [
    WorkflowStep(
        name="coding",
        role=ContainerRole.DEVELOPER,
        log_phase="coding",
        port=8001,
        description="Implement code changes",
        prompt_file="docker/developer.md",
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
        prompt_file="docker/evaluator.md",
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
        prompt_file="docker/qa.md",
        skip_if_complete=True,
        accepts_feedback=False,
        kanban_status="ai_testing",
        task_template="Run automated tests for {spec_name}"
    ),
]


def get_workflow() -> list[WorkflowStep]:
    """
    Get the configured workflow steps.

    Returns:
        List of workflow steps in execution order
    """
    # TODO: In the future, this could read from a config file or environment variable
    # For now, return the default workflow
    return DEFAULT_WORKFLOW


def get_step_by_phase(phase: str) -> Optional[WorkflowStep]:
    """
    Get workflow step by log phase name.

    Args:
        phase: Log phase name (coding, validation, testing)

    Returns:
        WorkflowStep if found, None otherwise
    """
    workflow = get_workflow()
    for step in workflow:
        if step.log_phase == phase:
            return step
    return None


def get_step_by_role(role: ContainerRole) -> Optional[WorkflowStep]:
    """
    Get workflow step by container role.

    Args:
        role: Container role

    Returns:
        WorkflowStep if found, None otherwise
    """
    workflow = get_workflow()
    for step in workflow:
        if step.role == role:
            return step
    return None


def get_step_by_name(name: str) -> Optional[WorkflowStep]:
    """
    Get workflow step by step name.

    Args:
        name: Step name (e.g., "coding", "code_review", "testing")

    Returns:
        WorkflowStep if found, None otherwise
    """
    workflow = get_workflow()
    for step in workflow:
        if step.name == name:
            return step
    return None
