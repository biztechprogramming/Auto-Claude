"""
Container Isolation Base Module
================================

Defines base classes and enums for Docker container-based workflow isolation.
Each container runs a specific role in the autonomous build pipeline.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ContainerRole(Enum):
    """
    Role of a container in the pipeline.

    Each role corresponds to a specific step in the autonomous workflow:
    - DATABASE_ANALYST: Analyzes database schema before coding
    - DEVELOPER: Implements code changes
    - EVALUATOR: Reviews code for quality and correctness
    - QA: Runs tests and validates implementation
    """

    DATABASE_ANALYST = "database_analyst"
    DEVELOPER = "developer"
    EVALUATOR = "evaluator"
    QA = "qa"


@dataclass
class ContainerConfig:
    """
    Configuration for a Docker container in the workflow.

    Attributes:
        role: The container's role in the pipeline
        image: Docker image name
        port: Port the container API listens on
        environment: Environment variables to pass to the container
        volumes: Volume mounts for the container
    """

    role: ContainerRole
    image: str
    port: Optional[int] = None
    environment: Optional[dict[str, str]] = None
    volumes: Optional[list[str]] = None

    def get_image_tag(self) -> str:
        """Get the full Docker image tag."""
        return f"auto-claude-{self.role.value}:latest"


@dataclass
class ContainerStatus:
    """
    Status of a running container.

    Attributes:
        container_id: Docker container ID
        role: Container role
        status: Current status (running, exited, etc.)
        port: Exposed port
        health: Health check status
    """

    container_id: str
    role: ContainerRole
    status: str
    port: Optional[int] = None
    health: str = "unknown"

    @property
    def is_running(self) -> bool:
        """Check if the container is running."""
        return self.status == "running"

    @property
    def is_healthy(self) -> bool:
        """Check if the container is healthy."""
        return self.health == "healthy"
