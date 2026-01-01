"""
Container Isolation Module
===========================

Provides Docker container-based isolation for the autonomous build pipeline.
Each step in the workflow runs in its own container with specific permissions.
"""

from .base import ContainerRole, ContainerConfig, ContainerStatus
from .workflow_config import (
    WorkflowStep,
    DEFAULT_WORKFLOW,
    get_workflow_steps,
    get_step_by_name,
    get_step_by_role,
    get_database_step,
    is_database_configured,
)

__all__ = [
    "ContainerRole",
    "ContainerConfig",
    "ContainerStatus",
    "WorkflowStep",
    "DEFAULT_WORKFLOW",
    "get_workflow_steps",
    "get_step_by_name",
    "get_step_by_role",
    "get_database_step",
    "is_database_configured",
]
