"""
Docker Orchestrator

Manages container lifecycle and coordinates the multi-container pipeline.
Runs on the host, outside of Docker containers.
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from .base import ContainerRole, ContainerResult, FeedbackComment
from .container_client import ContainerClient, ContainerConfig as ClientConfig
from .docker.image_builder import ImageBuilder
from .docker.container_manager import ContainerLifecycleManager


class DockerOrchestrator:
    """
    Orchestrates Docker containers for the isolation pipeline.

    Responsibilities:
    - Build container images
    - Create/destroy containers
    - Run containers with appropriate configuration
    - Collect results and feedback
    - Route feedback between containers
    """

    def __init__(
        self,
        project_dir: Path,
        base_branch: str,
        repo_url: str,
        images: dict[ContainerRole, str],
        memory_limit: str = "4g",
        cpu_shares: str = "1024",
        database_url: Optional[str] = None,
    ):
        self.project_dir = project_dir
        self.base_branch = base_branch
        self.repo_url = repo_url
        self.images = images
        self.memory_limit = memory_limit
        self.cpu_shares = cpu_shares
        self.database_url = database_url

        # Compose with specialized components
        self.image_builder = ImageBuilder()
        self.container_manager = ContainerLifecycleManager(
            memory_limit=memory_limit,
            cpu_shares=cpu_shares,
        )

    def _get_container_name(self, spec_name: str, role: ContainerRole) -> str:
        """Generate container name for a spec and role (delegates to container manager)."""
        return self.container_manager.get_container_name(spec_name, role)

    def _get_base_env_vars(self) -> dict:
        """Get base environment variables for all containers."""
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
            "REPO_URL": self.repo_url,
        }

        # GitHub authentication (gh CLI expects GH_TOKEN)
        github_token = os.environ.get("GH_TOKEN", "")
        if github_token:
            env["GH_TOKEN"] = github_token

        # Read-only database access
        if self.database_url:
            env["DATABASE_URL"] = self.database_url
            env["DATABASE_READ_ONLY"] = "true"

        return env

    def _extract_task_description(self, plan: dict, spec_name: str) -> str:
        """
        Extract a concise, human-readable task description from the implementation plan.

        Args:
            plan: The implementation plan dict
            spec_name: The spec name for fallback

        Returns:
            A clean, single-line task description suitable for commit messages
        """
        # Try to get feature name or spec name
        feature = plan.get("feature", spec_name)

        # Get first subtask description if available
        phases = plan.get("phases", [])
        if phases and len(phases) > 0:
            first_phase = phases[0]
            subtasks = first_phase.get("subtasks", [])
            if subtasks and len(subtasks) > 0:
                first_subtask = subtasks[0]
                description = first_subtask.get("description", "")
                if description:
                    # Limit to first sentence or 100 chars
                    if ". " in description:
                        description = description.split(". ")[0]
                    return description[:100]

        # Fallback to feature name
        return f"Implement {feature}"

    def build_images(self, force: bool = False) -> None:
        """
        Build all required Docker images (delegates to image builder).

        Args:
            force: If True, always rebuild. If False, only build if images don't exist
                   or if DOCKER_ALWAYS_REBUILD=true in .env
        """
        self.image_builder.build_all_images(images=self.images, force=force)

    def get_container_status(self, spec_name: str) -> dict[ContainerRole, str]:
        """
        Get status of all containers for a spec (delegates to container manager).

        Returns:
            Dict mapping role to status: "running", "stopped", "not_found"
        """
        return self.container_manager.get_container_status(spec_name)

    def cleanup_containers(self, spec_name: str) -> None:
        """Stop and remove all containers for a spec (delegates to container manager)."""
        self.container_manager.cleanup_containers(spec_name)

    async def _run_container_http(
        self,
        role: ContainerRole,
        spec_name: str,
        branch_name: str,
        task_description: str,
        feedback_comments: Optional[str] = None,
    ) -> ContainerResult:
        """
        Run a container via FastAPI HTTP communication.

        This provides real-time log visibility and better error handling.
        """
        import logging
        logger = logging.getLogger(__name__)

        # Get port from workflow config
        from core.isolation.workflow_config import get_step_by_role
        step = get_step_by_role(role)
        if not step:
            raise ValueError(f"No workflow step found for role: {role}")
        port = step.port

        # Create container config
        container_name = self._get_container_name(spec_name, role)
        env_vars = self._get_base_env_vars()

        config = ClientConfig(
            name=container_name,
            image=self.images[role],
            port=port,
            env_vars=env_vars
        )

        # Create client
        client = ContainerClient(config)

        # Setup task log writer (Observer pattern)
        from core.task_log_writer import TaskLogWriter
        spec_dir = self.project_dir / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True, exist_ok=True)

        log_writer = TaskLogWriter(spec_dir)

        # Get log phase from workflow config
        phase = step.log_phase

        # Set phase to active
        log_writer.set_phase_status(phase, "active")

        log_stream_process = None
        try:
            # Start container
            logger.info(f"Starting {role.value} container...")
            container_id = client.start_container()

            # Start streaming logs and observing them
            try:
                log_stream_process = subprocess.Popen(
                    ["docker", "logs", "-f", container_id],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1  # Line buffered
                )
                logger.info(f"Started log streaming (PID: {log_stream_process.pid})")

                # Start background thread to observe logs
                import threading
                def observe_logs():
                    try:
                        for line in log_stream_process.stdout:
                            log_writer.observe_container_log(phase, line.rstrip())
                    except Exception as e:
                        logger.warning(f"Log observation error: {e}")

                log_thread = threading.Thread(target=observe_logs, daemon=True)
                log_thread.start()

            except Exception as e:
                logger.warning(f"Failed to start log streaming: {e}")

            # Wait for API to be ready
            if not client.wait_for_ready(timeout=30):
                raise RuntimeError(f"{role.value} container API did not become ready")

            # Clone repository first
            logger.info(f"Cloning repository in {role.value} container...")
            await client.clone_repository(self.repo_url, branch_name)
            logger.info(f"Repository cloned successfully")

            # Prepare task data
            task_data = {
                "repo_url": self.repo_url,
                "base_branch": self.base_branch,
                "branch_name": branch_name,
                "spec_name": spec_name,
                "task_description": task_description,
                "feedback_comments": feedback_comments,
            }

            # Start task
            logger.info(f"Starting {role.value} task...")
            await client.start_task(task_data)

            # TODO: Stream logs in real-time (for now, just poll status)
            logger.info(f"Waiting for {role.value} to complete...")
            final_status = await client.wait_for_completion(timeout=600)  # 10 minute timeout

            # Get final logs
            logs = await client.get_logs(count=1000)
            output = "\n".join([f"[{log['level']}] {log['message']}" for log in logs])

            # Mark phase as complete
            log_writer.mark_phase_complete(phase, success=True)

            return ContainerResult(
                role=role,
                success=True,
                exit_code=0,
                output=output,
                commit_sha=None,  # TODO: Extract from logs if needed
            )

        except Exception as e:
            logger.error(f"{role.value} container failed: {e}")

            # Add error details to logs before marking phase as failed
            log_writer.add_log_entry(phase, f"Container error: {str(e)}", "error")

            # Mark phase as failed
            log_writer.mark_phase_complete(phase, success=False)

            # Try to get logs even on failure
            try:
                logs = await client.get_logs(count=1000)
                output = "\n".join([f"[{log['level']}] {log['message']}" for log in logs])
            except:
                output = str(e)

            return ContainerResult(
                role=role,
                success=False,
                exit_code=1,
                output=output,
                commit_sha=None,
            )

        finally:
            # Stop log streaming process
            if log_stream_process:
                try:
                    log_stream_process.terminate()
                    log_stream_process.wait(timeout=5)
                    logger.info("Log streaming stopped")
                except Exception as e:
                    logger.warning(f"Error stopping log stream: {e}")
                    try:
                        log_stream_process.kill()
                    except:
                        pass

            # Keep container running for review (don't stop it)
            pass

    async def run_developer(
        self,
        spec_name: str,
        branch_name: str,
        plan: dict,
        feedback_comments: list[FeedbackComment],
    ) -> ContainerResult:
        """
        Run the developer container via FastAPI HTTP communication.

        Uses FastAPI server running in container for:
        - Real-time log visibility
        - Better error handling
        - Structured communication

        1. Start FastAPI container
        2. POST task to /start endpoint
        3. Monitor /status for progress
        4. Stream /logs for real-time visibility
        5. Return results when complete
        """
        # Format feedback comments as JSON string for the container
        feedback_str = None
        if feedback_comments:
            feedback_str = json.dumps([
                {
                    "source": c.source.value,
                    "message": c.message,
                    "file_path": c.file_path,
                    "line_number": c.line_number,
                    "severity": c.severity,
                }
                for c in feedback_comments
            ])

        # Extract a concise task description from plan
        task_description = self._extract_task_description(plan, spec_name)

        # Use HTTP-based container communication
        return await self._run_container_http(
            role=ContainerRole.DEVELOPER,
            spec_name=spec_name,
            branch_name=branch_name,
            task_description=task_description,
            feedback_comments=feedback_str,
        )

    async def run_evaluator(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the evaluator container via HTTP-based communication.

        1. Clone the feature branch
        2. Run quality review prompts
        3. Return approval or rejection with comments
        """
        # Extract task description (placeholder for now)
        task_description = f"Review code quality for {spec_name}"

        # Use HTTP-based container communication (same as developer)
        return await self._run_container_http(
            role=ContainerRole.EVALUATOR,
            spec_name=spec_name,
            branch_name=branch_name,
            task_description=task_description,
            feedback_comments=None,
        )

    async def run_qa(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the QA container via HTTP-based communication.

        1. Clone the feature branch
        2. Run Playwright and other tests
        3. Return pass or failure with comments
        """
        # Extract task description (placeholder for now)
        task_description = f"Run automated tests for {spec_name}"

        # Use HTTP-based container communication (same as developer)
        return await self._run_container_http(
            role=ContainerRole.QA,
            spec_name=spec_name,
            branch_name=branch_name,
            task_description=task_description,
            feedback_comments=None,
        )
