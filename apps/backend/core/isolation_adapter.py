"""
Adapter between legacy workspace.py and new isolation system.

Preserves existing behavior while enabling Docker isolation.
This module provides a clean integration point without modifying core workspace code.
"""

import os
from pathlib import Path
from typing import Optional

from core.isolation import IsolationFactory, IsolationStrategy


def get_isolation_strategy(
    project_dir: Path,
    base_branch: Optional[str] = None,
) -> IsolationStrategy:
    """
    Get isolation strategy based on .env configuration.

    Reads ISOLATION_METHOD from environment:
    - "worktree" (default): Uses WorktreeIsolationStrategy
    - "docker": Uses DockerIsolationStrategy

    Args:
        project_dir: Project directory to isolate
        base_branch: Base branch for worktree/branching (auto-detected if None)

    Returns:
        IsolationStrategy instance configured based on environment
    """
    return IsolationFactory.create(
        project_dir=project_dir,
        base_branch=base_branch,
    )


def should_use_docker_isolation() -> bool:
    """
    Check if Docker isolation is enabled via environment variable.

    Returns:
        True if ISOLATION_METHOD=docker, False otherwise (default: worktree)
    """
    method = os.getenv("ISOLATION_METHOD", "worktree")
    return method.lower().strip() == "docker"


def is_docker_available() -> bool:
    """
    Check if Docker is available on the system.

    Returns:
        True if Docker is installed and accessible, False otherwise
    """
    return IsolationFactory.is_docker_available()
