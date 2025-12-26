"""
Docker container-based isolation strategy.

Uses a multi-container pipeline:
1. Developer container - implements changes
2. Evaluator container - code quality review
3. QA container - functional testing

All containers use ClaudeSDKClient for Claude interactions.
Work is shared via git only (no shared volumes).
Database access is read-only; migrations use golang-migrate.
"""

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .base import (
    IsolationStrategy,
    IsolationInfo,
    ContainerRole,
    ContainerResult,
    FeedbackComment,
)
from .orchestrator import DockerOrchestrator


class DockerIsolationStrategy(IsolationStrategy):
    """
    Isolation strategy using Docker containers.

    Pipeline:
    1. Orchestrator (host) creates implementation plan
    2. Developer container clones (depth=1), creates branch, implements, pushes
    3. Evaluator container clones feature branch, reviews quality
       - Approves → proceed to QA
       - Rejects → comments sent back, Developer container recreated
    4. QA container clones feature branch, runs Playwright tests
       - Passes → notify human for final review
       - Fails → comments sent back, Developer container recreated
    5. All state changes update kanban with comments
    """

    # Default image names
    DEFAULT_IMAGE_BASE = "auto-claude-base:latest"
    DEFAULT_IMAGE_DEVELOPER = "auto-claude-dev:latest"
    DEFAULT_IMAGE_EVALUATOR = "auto-claude-eval:latest"
    DEFAULT_IMAGE_QA = "auto-claude-qa:latest"

    # Resource limits
    DEFAULT_MEMORY = "4g"
    DEFAULT_CPU_SHARES = "1024"
    DEFAULT_PIDS_LIMIT = "256"

    def __init__(
        self,
        project_dir: Path,
        base_branch: Optional[str] = None,
        image_developer: Optional[str] = None,
        image_evaluator: Optional[str] = None,
        image_qa: Optional[str] = None,
        memory_limit: Optional[str] = None,
        cpu_shares: Optional[str] = None,
        repo_url: Optional[str] = None,
        database_url: Optional[str] = None,
        max_feedback_iterations: int = 3,
    ):
        super().__init__(project_dir, base_branch)

        # Container images (configurable)
        self.image_developer = image_developer or os.getenv(
            "DOCKER_IMAGE_DEVELOPER", self.DEFAULT_IMAGE_DEVELOPER
        )
        self.image_evaluator = image_evaluator or os.getenv(
            "DOCKER_IMAGE_EVALUATOR", self.DEFAULT_IMAGE_EVALUATOR
        )
        self.image_qa = image_qa or os.getenv(
            "DOCKER_IMAGE_QA", self.DEFAULT_IMAGE_QA
        )

        # Resource limits
        self.memory_limit = memory_limit or os.getenv(
            "DOCKER_MEMORY_LIMIT", self.DEFAULT_MEMORY
        )
        self.cpu_shares = cpu_shares or os.getenv(
            "DOCKER_CPU_SHARES", self.DEFAULT_CPU_SHARES
        )

        # Repository URL for cloning
        self.repo_url = repo_url or os.getenv("REPO_URL") or self._detect_repo_url()

        # Database (read-only)
        self.database_url = database_url or os.getenv("DATABASE_URL")

        # Feedback loop limit
        self.max_feedback_iterations = max_feedback_iterations

        # Detect base branch if not provided
        if not base_branch:
            base_branch = self._detect_base_branch()

        # Orchestrator
        self._orchestrator = DockerOrchestrator(
            project_dir=project_dir,
            base_branch=base_branch,
            repo_url=self.repo_url,
            images={
                ContainerRole.DEVELOPER: self.image_developer,
                ContainerRole.EVALUATOR: self.image_evaluator,
                ContainerRole.QA: self.image_qa,
            },
            memory_limit=self.memory_limit,
            cpu_shares=self.cpu_shares,
            database_url=self.database_url,
        )

    def _detect_repo_url(self) -> str:
        """Detect git remote URL."""
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        raise RuntimeError("Could not detect repository URL. Set REPO_URL env var.")

    def _detect_base_branch(self) -> str:
        """Detect the base branch (main/master/develop)."""
        for branch in ["main", "master", "develop"]:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                cwd=self.project_dir,
                capture_output=True,
            )
            if result.returncode == 0:
                return branch
        # No fallback - fail if none of the standard branches exist
        raise RuntimeError(
            "Could not detect base branch. None of 'main', 'master', or 'develop' exist. "
            "Create one of these branches or specify --base-branch explicitly."
        )

    def is_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def setup(self) -> None:
        """Ensure Docker is available and images are built."""
        if not self.is_docker_available():
            raise RuntimeError(
                "Docker is not available. Please install Docker or use worktree isolation."
            )

        # Build images if needed
        self._orchestrator.build_images()

    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create a branch for the spec (containers created on-demand)."""
        branch_name = f"auto-claude/{spec_name}"

        # Create branch on remote (via local git)
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.project_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", branch_name, self.base_branch],
            cwd=self.project_dir,
            capture_output=True,
            check=True,
        )

        return IsolationInfo(
            spec_name=spec_name,
            working_dir=self.project_dir,
            branch_name=branch_name,
            is_active=True,
        )

    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Check if environment (branch) exists."""
        branch_name = f"auto-claude/{spec_name}"
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=self.project_dir,
            capture_output=True,
        )
        if result.returncode != 0:
            return None

        return IsolationInfo(
            spec_name=spec_name,
            working_dir=self.project_dir,
            branch_name=branch_name,
            is_active=True,
        )

    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get or create environment."""
        existing = self.get_environment(spec_name)
        if existing:
            return existing
        return self.create_environment(spec_name)

    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the Docker-based multi-container pipeline.

        Flow:
        1. Developer container implements the plan
        2. Evaluator container reviews quality
        3. If rejected, loop back to Developer with comments
        4. QA container runs tests
        5. If failed, loop back to Developer with comments
        6. If all pass, notify human

        Kanban statuses:
        - "planning" → Planning implementation
        - "coding" → Developer implementing changes
        - "ai_review" → Evaluator reviewing code quality
        - "ai_testing" → QA running tests
        - "ready_for_review" → All checks passed, ready for human review
        - "needs_revision" → Failed checks, needs fixes
        - "failed" → Max iterations or critical error
        """
        env_info = self.get_or_create_environment(spec_name)
        branch_name = env_info.branch_name

        accumulated_comments: list[FeedbackComment] = []
        iteration = 0

        # Planning phase (if plan has subtasks, show them)
        if on_status_change:
            on_status_change(spec_name, "planning", "Creating implementation plan")

            # Show subtasks if available
            subtasks = plan.get("subtasks", [])
            if subtasks:
                subtask_summary = f"Plan: {len(subtasks)} subtasks"
                on_status_change(spec_name, "planning", subtask_summary)

        while iteration < self.max_feedback_iterations:
            iteration += 1

            # CODING PHASE - Developer container
            if on_status_change:
                if iteration == 1:
                    on_status_change(spec_name, "coding", "Implementing features...")
                else:
                    on_status_change(
                        spec_name, "coding",
                        f"Addressing feedback (iteration {iteration}/{self.max_feedback_iterations})"
                    )

            dev_result = await self._orchestrator.run_developer(
                spec_name=spec_name,
                branch_name=branch_name,
                plan=plan,
                feedback_comments=accumulated_comments,
            )

            if not dev_result.success:
                if on_status_change:
                    on_status_change(
                        spec_name, "failed",
                        f"Developer failed: {dev_result.output}"
                    )
                return False

            # Update with commit info
            if on_status_change and dev_result.commit_sha:
                on_status_change(
                    spec_name, "coding",
                    f"Completed - commit {dev_result.commit_sha[:7]}"
                )

            # AI REVIEW PHASE - Evaluator container
            if on_status_change:
                on_status_change(spec_name, "ai_review", "Reviewing code quality...")

            eval_result = await self._orchestrator.run_evaluator(
                spec_name=spec_name,
                branch_name=branch_name,
                commit_sha=dev_result.commit_sha,
            )

            if not eval_result.success:
                # Rejected - collect comments and loop back
                accumulated_comments.extend(eval_result.comments)
                if on_status_change:
                    on_status_change(
                        spec_name, "needs_revision",
                        f"AI Review rejected: {len(eval_result.comments)} issues found"
                    )
                continue  # Loop back to developer

            if on_status_change:
                on_status_change(spec_name, "ai_review", "✓ Code quality approved")

            # AI TESTING PHASE - QA container
            if on_status_change:
                on_status_change(spec_name, "ai_testing", "Running automated tests...")

            qa_result = await self._orchestrator.run_qa(
                spec_name=spec_name,
                branch_name=branch_name,
                commit_sha=dev_result.commit_sha,
            )

            if not qa_result.success:
                # Failed tests - collect comments and loop back
                accumulated_comments.extend(qa_result.comments)
                if on_status_change:
                    on_status_change(
                        spec_name, "needs_revision",
                        f"AI Testing failed: {len(qa_result.comments)} test failures"
                    )
                continue  # Loop back to developer

            if on_status_change:
                on_status_change(spec_name, "ai_testing", "✓ All tests passed")

            # All passed!
            if on_status_change:
                on_status_change(
                    spec_name, "ready_for_review",
                    f"All checks passed - ready for human review"
                )
            return True

        # Max iterations reached
        if on_status_change:
            on_status_change(
                spec_name, "failed",
                f"Max iterations ({self.max_feedback_iterations}) reached - needs manual review"
            )
        return False

    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Stop any running containers and optionally delete branch."""
        self._orchestrator.cleanup_containers(spec_name)

        if cleanup_branch:
            branch_name = f"auto-claude/{spec_name}"
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.project_dir,
                capture_output=True,
            )

    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """
        Merge spec branch to base branch.

        IMPORTANT: Always cleans up Docker containers, even if delete_after=False.
        Containers are temporary build artifacts and should be removed after merge.
        """
        branch_name = f"auto-claude/{spec_name}"
        base = self.base_branch or "main"

        # Checkout base branch
        result = subprocess.run(
            ["git", "checkout", base],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Failed to checkout base branch: {result.stderr}")
            return False

        # Merge spec branch
        result = subprocess.run(
            ["git", "merge", "--no-ff", branch_name, "-m", f"auto-claude: Merge {branch_name}"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Merge failed: {result.stderr}")
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.project_dir,
                capture_output=True,
            )
            return False

        # Always cleanup containers after successful merge
        print(f"Cleaning up Docker containers for {spec_name}...")
        self._orchestrator.cleanup_containers(spec_name)

        if delete_after:
            # Also delete the branch
            self.remove_environment(spec_name, cleanup_branch=True)

        return True

    def list_environments(self) -> list[IsolationInfo]:
        """List all spec branches."""
        result = subprocess.run(
            ["git", "branch", "--list", "auto-claude/*"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        environments = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            if not branch:
                continue
            spec_name = branch.replace("auto-claude/", "")
            environments.append(
                IsolationInfo(
                    spec_name=spec_name,
                    working_dir=self.project_dir,
                    branch_name=branch,
                    is_active=True,
                )
            )

        return environments

    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get changed files between base and spec branch."""
        branch_name = f"auto-claude/{spec_name}"
        base = self.base_branch or "main"

        result = subprocess.run(
            ["git", "diff", "--name-status", f"{base}...{branch_name}"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )

        files = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append((parts[0], parts[1]))
        return files

    def get_container_status(self, spec_name: str) -> dict:
        """
        Get status of all Docker containers for a spec.

        Returns:
            Dict with container status information:
            {
                "developer": "running" | "stopped" | "not_found",
                "evaluator": "running" | "stopped" | "not_found",
                "qa": "running" | "stopped" | "not_found"
            }
        """
        status = self._orchestrator.get_container_status(spec_name)
        return {role.value: state for role, state in status.items()}
