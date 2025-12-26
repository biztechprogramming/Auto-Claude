"""
Docker Orchestrator

Manages container lifecycle and coordinates the multi-container pipeline.
Runs on the host, outside of Docker containers.
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .base import ContainerRole, ContainerResult, FeedbackComment
from .container_client import ContainerClient, ContainerConfig as ClientConfig


@dataclass
class ContainerConfig:
    """Configuration for running a container."""
    image: str
    name: str
    role: ContainerRole
    env_vars: dict
    memory_limit: str
    cpu_shares: str


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

    def _get_container_name(self, spec_name: str, role: ContainerRole) -> str:
        """Generate container name for a spec and role."""
        return f"auto-claude-{spec_name}-{role.value}"

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

    def _image_exists(self, image_name: str) -> bool:
        """Check if a Docker image exists."""
        result = subprocess.run(
            ["docker", "images", "-q", image_name],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def build_images(self, force: bool = False) -> None:
        """
        Build all required Docker images.

        Args:
            force: If True, always rebuild. If False, only build if images don't exist
                   or if DOCKER_ALWAYS_REBUILD=true in .env
        """
        # Check configuration
        always_rebuild = os.environ.get("DOCKER_ALWAYS_REBUILD", "false").lower() == "true"
        should_build = force or always_rebuild

        dockerfile_dir = Path(__file__).parent.parent.parent / "docker"
        # Use apps/backend as build context so we can access prompts/
        build_context = Path(__file__).parent.parent.parent

        # Build base image first
        base_image = "auto-claude-base:latest"
        base_dockerfile = dockerfile_dir / "Dockerfile.base"

        if base_dockerfile.exists():
            if should_build or not self._image_exists(base_image):
                print(f"Building base image... (force={force}, always_rebuild={always_rebuild})")
                subprocess.run(
                    [
                        "docker", "build",
                        "-f", str(base_dockerfile),
                        "-t", base_image,
                        str(build_context),
                    ],
                    check=True,
                )
            else:
                print(f"Base image exists, skipping build (set DOCKER_ALWAYS_REBUILD=true to force)")

        # Build role-specific images
        for role, image in self.images.items():
            dockerfile = dockerfile_dir / f"Dockerfile.{role.value}"
            if dockerfile.exists():
                if should_build or not self._image_exists(image):
                    print(f"Building {role.value} image... (force={force}, always_rebuild={always_rebuild})")
                    subprocess.run(
                        [
                            "docker", "build",
                            "-f", str(dockerfile),
                            "-t", image,
                            str(build_context),
                        ],
                        check=True,
                    )
                else:
                    print(f"{role.value} image exists, skipping build")

    def _is_container_running(self, container_name: str) -> bool:
        """Check if a container is running."""
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def _container_exists(self, container_name: str) -> bool:
        """Check if a container exists (running or stopped)."""
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def get_container_status(self, spec_name: str) -> dict[ContainerRole, str]:
        """
        Get status of all containers for a spec.

        Returns:
            Dict mapping role to status: "running", "stopped", "not_found"
        """
        status = {}
        for role in ContainerRole:
            container_name = self._get_container_name(spec_name, role)
            if self._is_container_running(container_name):
                status[role] = "running"
            elif self._container_exists(container_name):
                status[role] = "stopped"
            else:
                status[role] = "not_found"
        return status

    def cleanup_containers(self, spec_name: str) -> None:
        """Stop and remove all containers for a spec."""
        for role in ContainerRole:
            container_name = self._get_container_name(spec_name, role)
            if self._container_exists(container_name):
                subprocess.run(
                    ["docker", "stop", container_name],
                    capture_output=True,
                )
                subprocess.run(
                    ["docker", "rm", container_name],
                    capture_output=True,
                )

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

        # Port mapping for each role
        port_map = {
            ContainerRole.DEVELOPER: 8001,
            ContainerRole.EVALUATOR: 8002,
            ContainerRole.QA: 8003,
        }
        port = port_map[role]

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

        try:
            # Start container
            logger.info(f"Starting {role.value} container...")
            client.start_container()

            # Wait for API to be ready
            if not client.wait_for_ready(timeout=30):
                raise RuntimeError(f"{role.value} container API did not become ready")

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

            return ContainerResult(
                role=role,
                success=True,
                exit_code=0,
                output=output,
                commit_sha=None,  # TODO: Extract from logs if needed
            )

        except Exception as e:
            logger.error(f"{role.value} container failed: {e}")

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

        # Use HTTP-based container communication
        return await self._run_container_http(
            role=ContainerRole.DEVELOPER,
            spec_name=spec_name,
            branch_name=branch_name,
            task_description=f"Implement plan: {json.dumps(plan)}",
            feedback_comments=feedback_str,
        )

    async def run_evaluator(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the evaluator container.

        1. Clone the feature branch
        2. Run quality review prompts
        3. Return approval or rejection with comments
        """
        container_name = self._get_container_name(spec_name, ContainerRole.EVALUATOR)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "COMMIT_SHA": commit_sha or "",
        })

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
        ]

        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.EVALUATOR],
            "python3", "/scripts/evaluator_agent.py",
        ])

        # Prevent MSYS path conversion on Windows (Git Bash)
        env = os.environ.copy()
        env["MSYS_NO_PATHCONV"] = "1"
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, env=env
        )

        # Parse output for approval/rejection and comments
        comments = []
        success = result.returncode == 0

        # Look for JSON feedback in output
        for line in result.stdout.split("\n"):
            if line.startswith("FEEDBACK_JSON="):
                try:
                    feedback = json.loads(line.split("=", 1)[1])
                    success = feedback.get("approved", False)
                    for c in feedback.get("comments", []):
                        comments.append(FeedbackComment(
                            source=ContainerRole.EVALUATOR,
                            message=c.get("message", ""),
                            file_path=c.get("file_path"),
                            line_number=c.get("line_number"),
                            severity=c.get("severity", "error"),
                        ))
                except json.JSONDecodeError:
                    pass
                break

        return ContainerResult(
            role=ContainerRole.EVALUATOR,
            success=success,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            comments=comments,
        )

    async def run_qa(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the QA container.

        1. Clone the feature branch
        2. Run Playwright and other tests
        3. Return pass or failure with comments
        """
        container_name = self._get_container_name(spec_name, ContainerRole.QA)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "COMMIT_SHA": commit_sha or "",
        })

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
            # QA container may need more resources for browser testing
            "--shm-size", "2g",
        ]

        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.QA],
            "python3", "/scripts/qa_agent.py",
        ])

        # Prevent MSYS path conversion on Windows (Git Bash)
        env = os.environ.copy()
        env["MSYS_NO_PATHCONV"] = "1"
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, env=env
        )

        # Parse output for pass/fail and comments
        comments = []
        success = result.returncode == 0

        for line in result.stdout.split("\n"):
            if line.startswith("FEEDBACK_JSON="):
                try:
                    feedback = json.loads(line.split("=", 1)[1])
                    success = feedback.get("passed", False)
                    for c in feedback.get("comments", []):
                        comments.append(FeedbackComment(
                            source=ContainerRole.QA,
                            message=c.get("message", ""),
                            file_path=c.get("file_path"),
                            line_number=c.get("line_number"),
                            severity=c.get("severity", "error"),
                        ))
                except json.JSONDecodeError:
                    pass
                break

        return ContainerResult(
            role=ContainerRole.QA,
            success=success,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            comments=comments,
        )
