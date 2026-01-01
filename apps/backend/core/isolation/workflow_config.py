"""
Workflow Configuration Module
==============================

Defines the workflow steps for the Docker-based autonomous build pipeline.
Each step runs in its own container and processes the task in sequence.
"""

from dataclasses import dataclass, field
from typing import Optional
from .base import ContainerRole


@dataclass
class WorkflowStep:
    """
    Configuration for a single step in the workflow pipeline.

    Attributes:
        name: Internal step identifier
        role: Container role for this step
        log_phase: Phase name for task logging (matches TaskLogPhase in frontend)
        port: Static port assignment (None for dynamic allocation)
        description: Human-readable description of the step
        prompt_file: Path to the system prompt file (relative to prompts/)
        skip_if_complete: Whether to skip this step if already completed
        accepts_feedback: Whether this step can receive feedback from later steps
        kanban_status: Kanban board status when this step is active
        task_template: Template for the task description
        preferred_port: Preferred port for dynamic allocation
        optional: Whether this step can be skipped if unavailable
        timeout_seconds: Maximum time for this step to complete
    """

    name: str
    role: ContainerRole
    log_phase: str
    port: Optional[int] = None
    description: str = ""
    prompt_file: str = ""
    skip_if_complete: bool = False
    accepts_feedback: bool = False
    kanban_status: str = ""
    task_template: str = ""
    preferred_port: int = 8000
    optional: bool = False
    timeout_seconds: int = 600
    environment_vars: list[str] = field(default_factory=list)

    def get_full_prompt_path(self) -> str:
        """Get the full path to the prompt file."""
        return f"prompts/{self.prompt_file}"

    @property
    def is_database_step(self) -> bool:
        """Check if this is the database analysis step."""
        return self.role == ContainerRole.DATABASE_ANALYST


# Default workflow configuration
# Database analysis runs first to provide schema context to developers
DEFAULT_WORKFLOW: list[WorkflowStep] = [
    # Step 0: Database Analysis (optional - runs before coding)
    WorkflowStep(
        name="database_analysis",
        role=ContainerRole.DATABASE_ANALYST,
        log_phase="database_analysis",
        port=None,  # Dynamically allocated
        description="Analyze database schema and data requirements",
        prompt_file="docker/database_analyst.md",
        skip_if_complete=True,
        accepts_feedback=False,
        kanban_status="analyzing",
        task_template="Analyze database schema for {spec_name}",
        preferred_port=8000,
        optional=True,  # Workflow continues if DB not configured
        timeout_seconds=300,  # 5 minutes for analysis
        environment_vars=[
            "PGHOST",
            "PGPORT",
            "PGUSER",
            "PGPASSWORD",
            "PGDATABASE",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_DATABASE",
        ],
    ),
    # Step 1: Development (coding)
    WorkflowStep(
        name="coding",
        role=ContainerRole.DEVELOPER,
        log_phase="coding",
        port=None,  # Dynamically allocated
        description="Implement code changes",
        prompt_file="docker/developer.md",
        skip_if_complete=True,
        accepts_feedback=True,
        kanban_status="coding",
        task_template="Implement features for {spec_name}",
        preferred_port=8001,
    ),
    # Step 2: Validation (code review)
    WorkflowStep(
        name="validation",
        role=ContainerRole.EVALUATOR,
        log_phase="validation",
        port=None,  # Dynamically allocated
        description="Review code for quality and correctness",
        prompt_file="docker/evaluator.md",
        skip_if_complete=False,
        accepts_feedback=False,
        kanban_status="validation",
        task_template="Review implementation for {spec_name}",
        preferred_port=8002,
    ),
    # Step 3: Testing (QA)
    WorkflowStep(
        name="testing",
        role=ContainerRole.QA,
        log_phase="testing",
        port=None,  # Dynamically allocated
        description="Run tests and validate implementation",
        prompt_file="docker/qa.md",
        skip_if_complete=False,
        accepts_feedback=False,
        kanban_status="testing",
        task_template="Test implementation for {spec_name}",
        preferred_port=8003,
    ),
]


def get_workflow_steps(include_optional: bool = True) -> list[WorkflowStep]:
    """
    Get the list of workflow steps.

    Args:
        include_optional: Whether to include optional steps like database analysis

    Returns:
        List of workflow steps in execution order
    """
    if include_optional:
        return DEFAULT_WORKFLOW.copy()
    return [step for step in DEFAULT_WORKFLOW if not step.optional]


def get_step_by_name(name: str) -> Optional[WorkflowStep]:
    """
    Get a workflow step by its name.

    Args:
        name: Step name to find

    Returns:
        WorkflowStep if found, None otherwise
    """
    for step in DEFAULT_WORKFLOW:
        if step.name == name:
            return step
    return None


def get_step_by_role(role: ContainerRole) -> Optional[WorkflowStep]:
    """
    Get a workflow step by its container role.

    Args:
        role: Container role to find

    Returns:
        WorkflowStep if found, None otherwise
    """
    for step in DEFAULT_WORKFLOW:
        if step.role == role:
            return step
    return None


def get_database_step() -> Optional[WorkflowStep]:
    """
    Get the database analysis step.

    Returns:
        The database analysis WorkflowStep or None if not configured
    """
    return get_step_by_role(ContainerRole.DATABASE_ANALYST)


def is_database_configured() -> bool:
    """
    Check if database environment variables are configured.

    Returns:
        True if at least PostgreSQL or MySQL credentials are available
    """
    import os

    # Check PostgreSQL
    pg_configured = all(
        os.environ.get(var)
        for var in ["PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE"]
    )

    # Check MySQL
    mysql_configured = all(
        os.environ.get(var)
        for var in ["MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"]
    )

    return pg_configured or mysql_configured
