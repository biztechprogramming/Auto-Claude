"""
Base classes for isolation strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ContainerRole(Enum):
    """Role of a container in the pipeline."""
    DEVELOPER = "developer"
    EVALUATOR = "evaluator"
    QA = "qa"


@dataclass
class FeedbackComment:
    """Feedback from evaluator or QA back to developer."""
    source: ContainerRole
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    severity: str = "error"  # error, warning, suggestion


@dataclass
class ContainerResult:
    """Result from a container execution."""
    role: ContainerRole
    success: bool
    exit_code: int
    output: str
    comments: list[FeedbackComment] = field(default_factory=list)
    commit_sha: Optional[str] = None  # For developer container


@dataclass
class IsolationInfo:
    """Information about an isolated execution environment."""
    spec_name: str
    working_dir: Path
    branch_name: str
    is_active: bool = True
    # Strategy-specific metadata
    container_id: Optional[str] = None  # Docker only
    container_role: Optional[ContainerRole] = None  # Docker only
    worktree_path: Optional[Path] = None  # Worktree only


class IsolationStrategy(ABC):
    """
    Abstract base class for isolation strategies.

    Both WorktreeIsolationStrategy and DockerIsolationStrategy
    implement this interface, allowing the runner to use either
    without knowing the implementation details.
    """

    def __init__(self, project_dir: Path, base_branch: Optional[str] = None):
        self.project_dir = project_dir
        self.base_branch = base_branch

    @abstractmethod
    def setup(self) -> None:
        """Initialize the isolation strategy (create directories, build images, etc.)."""
        pass

    @abstractmethod
    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create an isolated environment for a spec."""
        pass

    @abstractmethod
    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Get info about an existing environment, or None if it doesn't exist."""
        pass

    @abstractmethod
    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get existing environment or create a new one."""
        pass

    @abstractmethod
    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the full implementation pipeline.

        For worktree: planner → coder → qa_reviewer → qa_fixer
        For docker: developer → evaluator → qa (with feedback loops)

        Args:
            spec_name: The spec being implemented
            plan: The implementation plan
            on_status_change: Callback for kanban status updates

        Returns:
            True if pipeline completed successfully
        """
        pass

    @abstractmethod
    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Remove an isolated environment."""
        pass

    @abstractmethod
    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """Merge changes from the isolated environment back to base branch."""
        pass

    @abstractmethod
    def list_environments(self) -> list[IsolationInfo]:
        """List all active isolated environments."""
        pass

    @abstractmethod
    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get list of changed files (status, path) in the environment."""
        pass
