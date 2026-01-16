"""
Docker container lifecycle manager.

Handles starting, stopping, and status checking of Docker containers.
Separated from orchestrator to allow focused lifecycle management.
"""

import subprocess
from dataclasses import dataclass
from typing import Optional

from ..base import ContainerRole


@dataclass
class ContainerConfig:
    """Configuration for a container instance."""
    name: str
    image: str
    port: int
    env_vars: dict
    memory_limit: str = "4g"
    cpu_shares: str = "1024"
    pids_limit: str = "256"


class ContainerLifecycleManager:
    """
    Manages Docker container lifecycle operations.

    Responsibilities:
    - Start containers with proper configuration
    - Stop and remove containers
    - Check container status
    - Generate container names for specs
    """

    def __init__(self, memory_limit: str = "4g", cpu_shares: str = "1024"):
        """
        Initialize the lifecycle manager.

        Args:
            memory_limit: Default memory limit for containers
            cpu_shares: Default CPU shares for containers
        """
        self.memory_limit = memory_limit
        self.cpu_shares = cpu_shares

    def get_container_name(self, spec_name: str, role: ContainerRole) -> str:
        """
        Generate container name for a spec and role.

        Args:
            spec_name: Name of the spec
            role: Container role (developer, evaluator, qa)

        Returns:
            Container name string
        """
        return f"auto-claude-{spec_name}-{role.value}"

    def container_exists(self, container_name: str) -> bool:
        """
        Check if a container exists (running or stopped).

        Args:
            container_name: Name of the container

        Returns:
            True if container exists, False otherwise
        """
        result = subprocess.run(
            ["docker", "ps", "-a", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def is_container_running(self, container_name: str) -> bool:
        """
        Check if a container is currently running.

        Args:
            container_name: Name of the container

        Returns:
            True if container is running, False otherwise
        """
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name={container_name}"],
            capture_output=True,
            text=True,
        )
        return bool(result.stdout.strip())

    def get_container_status(self, spec_name: str) -> dict[ContainerRole, str]:
        """
        Get status of all containers for a spec.

        Args:
            spec_name: Name of the spec

        Returns:
            Dict mapping role to status: "running", "stopped", "not_found"
        """
        status = {}
        for role in ContainerRole:
            container_name = self.get_container_name(spec_name, role)
            if self.is_container_running(container_name):
                status[role] = "running"
            elif self.container_exists(container_name):
                status[role] = "stopped"
            else:
                status[role] = "not_found"
        return status

    def stop_container(self, container_name: str) -> None:
        """
        Stop a running container.

        Args:
            container_name: Name of the container to stop
        """
        if self.is_container_running(container_name):
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
            )

    def remove_container(self, container_name: str) -> None:
        """
        Remove a container (must be stopped first).

        Args:
            container_name: Name of the container to remove
        """
        if self.container_exists(container_name):
            subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
            )

    def cleanup_container(self, container_name: str) -> None:
        """
        Stop and remove a container.

        Args:
            container_name: Name of the container to cleanup
        """
        self.stop_container(container_name)
        self.remove_container(container_name)

    def cleanup_containers(self, spec_name: str) -> None:
        """
        Stop and remove all containers for a spec.

        Args:
            spec_name: Name of the spec
        """
        for role in ContainerRole:
            container_name = self.get_container_name(spec_name, role)
            self.cleanup_container(container_name)

    def start_container(
        self,
        config: ContainerConfig,
        additional_docker_args: Optional[list[str]] = None,
    ) -> str:
        """
        Start a Docker container with the given configuration.

        Args:
            config: Container configuration
            additional_docker_args: Optional additional arguments to docker run

        Returns:
            Container ID

        Raises:
            RuntimeError: If container fails to start
        """
        # Build docker run command
        cmd = [
            "docker", "run",
            "-d",  # Detached mode
            "--name", config.name,
            "-p", f"{config.port}:{config.port}",
            "--memory", config.memory_limit,
            "--cpu-shares", config.cpu_shares,
            "--pids-limit", config.pids_limit,
        ]

        # Add environment variables
        for key, value in config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add any additional arguments
        if additional_docker_args:
            cmd.extend(additional_docker_args)

        # Add image
        cmd.append(config.image)

        # Remove existing container if it exists
        if self.container_exists(config.name):
            self.cleanup_container(config.name)

        # Run container
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container {config.name}: {result.stderr}")

        container_id = result.stdout.strip()
        return container_id
