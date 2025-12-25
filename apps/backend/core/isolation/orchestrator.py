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

        # Read-only database access
        if self.database_url:
            env["DATABASE_URL"] = self.database_url
            env["DATABASE_READ_ONLY"] = "true"

        return env

    def build_images(self) -> None:
        """Build all required Docker images."""
        dockerfile_dir = Path(__file__).parent.parent.parent / "docker"

        # Build base image first
        base_dockerfile = dockerfile_dir / "Dockerfile.base"
        if base_dockerfile.exists():
            print("Building base image...")
            subprocess.run(
                [
                    "docker", "build",
                    "-f", str(base_dockerfile),
                    "-t", "auto-claude-base:latest",
                    str(dockerfile_dir),
                ],
                check=True,
            )

        # Build role-specific images
        for role, image in self.images.items():
            dockerfile = dockerfile_dir / f"Dockerfile.{role.value}"
            if dockerfile.exists():
                print(f"Building {role.value} image...")
                subprocess.run(
                    [
                        "docker", "build",
                        "-f", str(dockerfile),
                        "-t", image,
                        str(dockerfile_dir),
                    ],
                    check=True,
                )

    def cleanup_containers(self, spec_name: str) -> None:
        """Stop and remove all containers for a spec."""
        for role in ContainerRole:
            container_name = self._get_container_name(spec_name, role)
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
            )
            subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
            )

    async def run_developer(
        self,
        spec_name: str,
        branch_name: str,
        plan: dict,
        feedback_comments: list[FeedbackComment],
    ) -> ContainerResult:
        """
        Run the developer container.

        1. Clone repo with depth=1
        2. Create/checkout feature branch
        3. Implement the plan (addressing any feedback)
        4. Commit and push changes
        """
        container_name = self._get_container_name(spec_name, ContainerRole.DEVELOPER)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "BASE_BRANCH": self.base_branch,
            "IMPLEMENTATION_PLAN": json.dumps(plan),
        })

        # Include feedback if any
        if feedback_comments:
            env_vars["FEEDBACK_COMMENTS"] = json.dumps([
                {
                    "source": c.source.value,
                    "message": c.message,
                    "file_path": c.file_path,
                    "line_number": c.line_number,
                    "severity": c.severity,
                }
                for c in feedback_comments
            ])

        # Build docker run command
        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
        ]

        # Add environment variables
        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.DEVELOPER],
            "python", "/scripts/developer_agent.py",
        ])

        # Run container
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )

        # Parse output for commit SHA
        commit_sha = None
        for line in result.stdout.split("\n"):
            if line.startswith("COMMIT_SHA="):
                commit_sha = line.split("=", 1)[1].strip()
                break

        return ContainerResult(
            role=ContainerRole.DEVELOPER,
            success=result.returncode == 0,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            commit_sha=commit_sha,
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
            "python", "/scripts/evaluator_agent.py",
        ])

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
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
            "python", "/scripts/qa_agent.py",
        ])

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
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
