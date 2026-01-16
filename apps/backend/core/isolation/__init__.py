"""
Isolation Strategy Module
=========================

Provides pluggable isolation strategies for running agent sessions.
Supports both Git worktree and Docker container isolation.
"""

from .base import IsolationStrategy, IsolationInfo, ContainerRole
from .factory import IsolationFactory
from .worktree_strategy import WorktreeIsolationStrategy
from .docker_strategy import DockerIsolationStrategy
from .orchestrator import DockerOrchestrator

__all__ = [
    "IsolationStrategy",
    "IsolationInfo",
    "ContainerRole",
    "IsolationFactory",
    "WorktreeIsolationStrategy",
    "DockerIsolationStrategy",
    "DockerOrchestrator",
]
