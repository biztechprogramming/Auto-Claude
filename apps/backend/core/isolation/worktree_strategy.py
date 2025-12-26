"""
Worktree-based isolation strategy.

This wraps the existing WorktreeManager and agent execution code,
maintaining full backward compatibility while conforming to the
IsolationStrategy interface.

Security: Uses ClaudeSDKClient with configurable permissions,
sandbox enabled, and bash_security_hook for command validation.
"""

import os
from pathlib import Path
from typing import Optional

from .base import IsolationStrategy, IsolationInfo
from core.worktree import WorktreeManager


class WorktreeIsolationStrategy(IsolationStrategy):
    """
    Isolation strategy using Git worktrees.

    Delegates to existing WorktreeManager for worktree operations
    and existing agent code for execution. This maintains the
    current security model:
    - Sandbox enabled (OS-level bash isolation)
    - File permissions restricted to project directory
    - Bash commands validated via bash_security_hook
    - Configurable permission overrides via settings
    """

    def __init__(
        self,
        project_dir: Path,
        base_branch: Optional[str] = None,
        permission_overrides: Optional[dict] = None,
    ):
        super().__init__(project_dir, base_branch)
        self._manager = WorktreeManager(project_dir, base_branch)
        self._permission_overrides = permission_overrides or {}

    def setup(self) -> None:
        """Initialize worktrees directory."""
        self._manager.setup()

    def get_permission_settings(self) -> dict:
        """
        Get permission settings for the SDK client.

        Merges default permissions with any configured overrides.
        """
        # Default permissions (from current client.py)
        default_permissions = {
            "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
            "permissions": {
                "defaultMode": "acceptEdits",
                "allow": [
                    "Read(./**)",
                    "Write(./**)",
                    "Edit(./**)",
                    "Glob(./**)",
                    "Grep(./**)",
                    "Bash(*)",
                ],
            },
        }

        # Apply overrides
        if self._permission_overrides:
            if "permissions" in self._permission_overrides:
                override_perms = self._permission_overrides["permissions"]
                if "allow" in override_perms:
                    # Extend or replace allow list
                    if override_perms.get("extend_allow", False):
                        default_permissions["permissions"]["allow"].extend(
                            override_perms["allow"]
                        )
                    else:
                        default_permissions["permissions"]["allow"] = override_perms["allow"]
                if "deny" in override_perms:
                    default_permissions["permissions"]["deny"] = override_perms["deny"]

            if "sandbox" in self._permission_overrides:
                default_permissions["sandbox"].update(self._permission_overrides["sandbox"])

        return default_permissions

    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create a worktree for the spec."""
        info = self._manager.create_worktree(spec_name)
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Get worktree info if it exists."""
        info = self._manager.get_worktree_info(spec_name)
        if info is None:
            return None
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get or create worktree."""
        info = self._manager.get_or_create_worktree(spec_name)
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the worktree-based pipeline.

        Uses existing agent code: planner → coder → qa_reviewer → qa_fixer
        """
        # Import here to avoid circular imports
        from agents import run_autonomous_agent

        env_info = self.get_or_create_environment(spec_name)

        # Run the existing autonomous agent pipeline
        # This handles the full planner → coder → qa_reviewer → qa_fixer flow
        success = await run_autonomous_agent(
            spec_dir=self.project_dir / ".auto-claude" / "specs" / spec_name,
            project_dir=env_info.working_dir,
            source_spec_dir=self.project_dir / ".auto-claude" / "specs" / spec_name,
        )

        if on_status_change:
            status = "completed" if success else "failed"
            on_status_change(spec_name, status)

        return success

    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Remove worktree."""
        self._manager.remove_worktree(spec_name, delete_branch=cleanup_branch)

    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """Merge worktree branch to base."""
        return self._manager.merge_worktree(spec_name, delete_after=delete_after)

    def list_environments(self) -> list[IsolationInfo]:
        """List all worktrees."""
        worktrees = self._manager.list_all_worktrees()
        return [
            IsolationInfo(
                spec_name=w.spec_name,
                working_dir=w.path,
                branch_name=w.branch,
                is_active=w.is_active,
                worktree_path=w.path,
            )
            for w in worktrees
        ]

    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get changed files in worktree."""
        return self._manager.get_changed_files(spec_name)
