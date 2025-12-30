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
            # Update the base class attribute since we detected it after calling super().__init__
            self.base_branch = base_branch
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
        """Detect git remote URL and convert SSH to HTTPS for Docker."""
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Convert SSH URLs to HTTPS for Docker containers
            # git@github.com:user/repo.git -> https://github.com/user/repo.git
            if url.startswith("git@"):
                url = url.replace(":", "/", 1).replace("git@", "https://")
            return url
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

        State machine implementation using WorkflowStepState:
        - PENDING → ACTIVE → COMPLETED → [Next Step]
        - PENDING → ACTIVE → FAILED → [Retry if accepts_feedback] → ACTIVE
        - PENDING → SKIPPED → [Next Step] (if already completed)
        """
        from core.isolation.workflow_config import get_workflow
        from core.isolation.workflow_state import (
            create_workflow_states,
            StepStatus,
            all_steps_complete,
        )
        from core.task_log_writer import TaskLogWriter
        import json

        env_info = self.get_or_create_environment(spec_name)
        branch_name = env_info.branch_name

        # Initialize task log writer
        spec_dir = self.project_dir / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True, exist_ok=True)
        log_writer = TaskLogWriter(spec_dir)

        # Create workflow states from configuration
        workflow_steps = get_workflow()
        workflow_states = create_workflow_states(workflow_steps)

        # Check if any steps are already completed (from previous runs)
        for step_state in workflow_states:
            if step_state.config.skip_if_complete and log_writer.is_phase_complete(step_state.log_phase):
                step_state.skip()

        accumulated_comments: list[FeedbackComment] = []
        iteration = 0

        # Planning phase (if plan has subtasks, show them)
        log_writer.update_workflow_state("planning", current_step=None, iteration=0)

        if on_status_change:
            on_status_change(spec_name, "planning", "Creating implementation plan")

            # Show subtasks if available
            subtasks = plan.get("subtasks", [])
            if subtasks:
                subtask_summary = f"Plan: {len(subtasks)} subtasks"
                on_status_change(spec_name, "planning", subtask_summary)

        # Mark planning phase as complete before starting workflow
        log_writer.mark_phase_complete("planning", success=True)
        log_writer.add_log_entry("planning", "Implementation plan ready", "info")

        # Main iteration loop
        while iteration < self.max_feedback_iterations:
            iteration += 1
            log_writer.set_iteration(iteration)

            # Execute each step in the workflow
            for step_state in workflow_states:
                # Skip if already completed
                if step_state.is_complete:
                    if step_state.status == StepStatus.SKIPPED and iteration == 1:
                        # Only log skipping on first iteration
                        if on_status_change:
                            on_status_change(
                                spec_name,
                                step_state.config.kanban_status,
                                f"{step_state.description} - already completed, skipping"
                            )
                        log_writer.add_log_entry(
                            step_state.log_phase,
                            f"Skipping {step_state.description} (already completed)",
                            "info"
                        )
                    continue

                # Start the step
                step_state.start(iteration)
                log_writer.set_current_step(step_state.name)

                # Update status for UI
                if on_status_change:
                    if iteration == 1:
                        on_status_change(spec_name, step_state.config.kanban_status, step_state.description)
                    else:
                        on_status_change(
                            spec_name,
                            step_state.config.kanban_status,
                            f"{step_state.description} (retry {iteration}/{self.max_feedback_iterations})"
                        )

                # Load the full spec content
                spec_file = spec_dir / "spec.md"
                spec_content = ""
                if spec_file.exists():
                    spec_content = spec_file.read_text(encoding="utf-8")
                else:
                    # Fallback: use task description from template
                    spec_content = step_state.config.task_template.format(spec_name=spec_name)

                # Format feedback comments as JSON string if step accepts feedback
                feedback_str = None
                if step_state.config.accepts_feedback and accumulated_comments:
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
                    role=step_state.config.role,
                    spec_name=spec_name,
                    branch_name=branch_name,
                    spec_content=spec_content,
                    feedback_comments=feedback_str,
                )

                # Handle step result
                if not result.success:
                    # Step failed
                    step_state.fail(result.output)

                    # Case 1: Step accepts feedback AND we have iterations left
                    if step_state.can_retry and iteration < self.max_feedback_iterations:
                        # Collect feedback comments for next iteration
                        accumulated_comments.extend(result.comments)

                        # Log the failure reason
                        log_writer.add_log_entry(
                            step_state.log_phase,
                            f"{step_state.description} failed: {len(result.comments)} issues found",
                            "error"
                        )

                        # Update workflow status to needs_revision
                        log_writer.set_workflow_status("needs_revision")

                        if on_status_change:
                            on_status_change(
                                spec_name, "needs_revision",
                                f"{step_state.description} failed: {len(result.comments)} issues found - will retry"
                            )

                        # Reset all non-skipped steps to pending for retry
                        for s in workflow_states:
                            if s.status not in (StepStatus.SKIPPED, StepStatus.PENDING):
                                s.status = StepStatus.PENDING
                                s.started_at = None
                                s.completed_at = None
                                s.error = None

                        # Break inner loop to retry from beginning
                        break

                    # Case 2: No retry available - fail permanently
                    else:
                        # Log the permanent failure
                        log_writer.add_log_entry(
                            step_state.log_phase,
                            f"{step_state.description} failed permanently (no retry available)",
                            "error"
                        )

                        # Update workflow status to failed
                        log_writer.set_workflow_status("failed")

                        if on_status_change:
                            on_status_change(
                                spec_name, "failed",
                                f"{step_state.description} failed - no retry available"
                            )

                        # Exit the pipeline
                        return False

                # Step succeeded
                else:
                    step_state.complete(result.commit_sha)

                    # Log success
                    log_writer.add_log_entry(
                        step_state.log_phase,
                        f"✓ {step_state.description} completed successfully",
                        "success"
                    )

                    # Update the workflow status (after step completes)
                    log_writer.set_workflow_status(step_state.config.kanban_status)

                    # Update UI status
                    if on_status_change:
                        on_status_change(
                            spec_name,
                            step_state.config.kanban_status,
                            f"✓ {step_state.description} completed"
                        )

            # Check if all steps are complete
            if all_steps_complete(workflow_states):
                # All steps passed! Update workflow status to ready_for_review
                log_writer.set_workflow_status("ready_for_review")
                log_writer.set_current_step(None)  # No current step when complete

                log_writer.add_log_entry(
                    "testing",  # Add to last phase
                    "All workflow steps completed successfully",
                    "success"
                )

                if on_status_change:
                    on_status_change(
                        spec_name, "ready_for_review",
                        "All checks passed - ready for human review"
                    )
                return True

            # If we got here without all steps complete, continue to next iteration

        # Max iterations reached without success
        log_writer.set_workflow_status("failed")
        log_writer.set_current_step(None)

        log_writer.add_log_entry(
            "coding",  # Add to first phase as general error
            f"Max iterations ({self.max_feedback_iterations}) reached without success",
            "error"
        )

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
