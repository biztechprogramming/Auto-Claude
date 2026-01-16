"""
Factory for creating isolation strategies based on settings.
"""

import os
from pathlib import Path
from typing import Optional

from .base import IsolationStrategy
from .worktree_strategy import WorktreeIsolationStrategy
from .docker_strategy import DockerIsolationStrategy


class IsolationFactory:
    """
    Factory for creating isolation strategies.

    Reads ISOLATION_METHOD from environment/settings and returns
    the appropriate strategy implementation.
    """

    WORKTREE = "worktree"
    DOCKER = "docker"

    @classmethod
    def create(
        cls,
        project_dir: Path,
        base_branch: Optional[str] = None,
        method: Optional[str] = None,
        **kwargs,
    ) -> IsolationStrategy:
        """
        Create an isolation strategy based on settings.

        Args:
            project_dir: The project directory to isolate
            base_branch: Base branch for branching (auto-detected if None)
            method: Override isolation method ("worktree" or "docker")
                    If None, reads from ISOLATION_METHOD env var
            **kwargs: Additional arguments passed to the strategy

        Returns:
            IsolationStrategy implementation
        """
        if method is None:
            method = os.getenv("ISOLATION_METHOD", cls.WORKTREE)

        method = method.lower().strip()

        if method == cls.DOCKER:
            return DockerIsolationStrategy(
                project_dir=project_dir,
                base_branch=base_branch,
                **kwargs,
            )
        elif method == cls.WORKTREE:
            return WorktreeIsolationStrategy(
                project_dir=project_dir,
                base_branch=base_branch,
                **kwargs,
            )
        else:
            raise ValueError(
                f"Unknown isolation method: {method}. "
                f"Use '{cls.WORKTREE}' or '{cls.DOCKER}'."
            )

    @classmethod
    def get_available_methods(cls) -> list[str]:
        """Return list of available isolation methods."""
        return [cls.WORKTREE, cls.DOCKER]

    @classmethod
    def is_docker_available(cls) -> bool:
        """Check if Docker isolation is available."""
        try:
            strategy = DockerIsolationStrategy(Path("."))
            return strategy.is_docker_available()
        except Exception:
            return False
