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
        print(f"[DockerStrategy] repo_url={self.repo_url}, type={type(self.repo_url)}")

        # Database (read-only)
        self.database_url = database_url or os.getenv("DATABASE_URL")
        print(f"[DockerStrategy] database_url={self.database_url}, type={type(self.database_url)}")

        # Feedback loop limit
        self.max_feedback_iterations = max_feedback_iterations

        # Detect base branch if not provided
        if not base_branch:
            base_branch = self._detect_base_branch()
        print(f"[DockerStrategy] base_branch={base_branch}, type={type(base_branch)}")

        # Log all values before creating orchestrator
        print(f"[DockerStrategy] Creating orchestrator with:")
        print(f"  project_dir={self.project_dir}")
        print(f"  base_branch={base_branch}")
        print(f"  repo_url={self.repo_url}")
        print(f"  memory_limit={self.memory_limit}")
        print(f"  cpu_shares={self.cpu_shares}")
        print(f"  database_url={self.database_url}")

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
        """Get the current branch."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != "HEAD":
                return branch
        # Fallback if detached HEAD or error
        raise RuntimeError(
            "Could not detect current branch. "
            "Ensure you're on a branch or specify --base-branch explicitly."
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

    def _is_phase_complete(self, spec_name: str, phase: str) -> bool:
        """
        Check if a phase is already completed by reading task_logs.json.

        Args:
            spec_name: The spec name
            phase: The phase name (coding, validation, testing)

        Returns:
            True if phase is marked as completed
        """
        import json
        log_file = self.project_dir / ".auto-claude" / "specs" / spec_name / "task_logs.json"

        if not log_file.exists():
            return False

        try:
            with open(log_file, 'r') as f:
                logs = json.load(f)

            phase_status = logs.get("phases", {}).get(phase, {}).get("status")
            return phase_status == "completed"
        except Exception:
            return False

    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the Docker-based multi-container pipeline using workflow configuration.

        The workflow is defined in workflow_config.py and can be customized.
        Each step runs in sequence, with feedback loops for steps that accept feedback.
        """
        from core.isolation.workflow_config import get_workflow

        env_info = self.get_or_create_environment(spec_name)
        branch_name = env_info.branch_name

        # Get workflow steps
        workflow = get_workflow()

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

            # Execute each step in the workflow
            results = {}

            for step in workflow:
                # Check if step should be skipped
                if iteration == 1 and step.skip_if_complete and self._is_phase_complete(spec_name, step.log_phase):
                    if on_status_change:
                        on_status_change(spec_name, step.kanban_status, f"{step.description} - already completed, skipping")
                    # Create mock success result
                    results[step.name] = ContainerResult(
                        role=step.role,
                        success=True,
                        exit_code=0,
                        output=f"{step.log_phase} phase already completed",
                        commit_sha=None,
                    )
                    continue

                # Update status
                if on_status_change:
                    if iteration == 1:
                        on_status_change(spec_name, step.kanban_status, step.description)
                    else:
                        on_status_change(
                            spec_name, step.kanban_status,
                            f"{step.description} (iteration {iteration}/{self.max_feedback_iterations})"
                        )

                # Prepare task description
                task_description = step.task_template.format(spec_name=spec_name)

                # Format feedback comments as JSON string if step accepts feedback
                import json
                feedback_str = None
                if step.accepts_feedback and accumulated_comments:
                    feedback_str = json.dumps([
                        {
                            "source": c.source.value,
                            "message": c.message,
                            "file_path": c.file_path,
                            "line_number": c.line_number,
                            "severity": c.severity,
                        }
                        for c in accumulated_comments
                    ])

                # Run the container step
                result = await self._orchestrator._run_container_http(
                    role=step.role,
                    spec_name=spec_name,
                    branch_name=branch_name,
                    task_description=task_description,
                    feedback_comments=feedback_str,
                )

                results[step.name] = result

                # Handle failure
                if not result.success:
                    # If step accepts feedback and we have iterations left, collect comments and retry
                    if step.accepts_feedback and iteration < self.max_feedback_iterations:
                        accumulated_comments.extend(result.comments)
                        if on_status_change:
                            on_status_change(
                                spec_name, "needs_revision",
                                f"{step.description} failed: {len(result.comments)} issues found"
                            )
                        break  # Break inner loop, will retry in next iteration
                    else:
                        # No retry, fail the pipeline
                        if on_status_change:
                            on_status_change(
                                spec_name, "failed",
                                f"{step.description} failed"
                            )
                        return False

                # Update success status
                if on_status_change:
                    on_status_change(spec_name, step.kanban_status, f"✓ {step.description} completed")

            # Check if all steps succeeded
            all_succeeded = all(r.success for r in results.values())

            if all_succeeded:
                # All steps passed!
                if on_status_change:
                    on_status_change(
                        spec_name, "ready_for_review",
                        "All checks passed - ready for human review"
                    )
                return True

            # If we got here, a step failed and we need to retry (continue loop)

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
