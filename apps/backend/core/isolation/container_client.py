"""
HTTP client for communicating with FastAPI-based Docker containers.

Provides real-time log streaming and status monitoring.
"""

import time
import json
import asyncio
import logging
import subprocess
from typing import Optional
from dataclasses import dataclass

import httpx
import websockets

logger = logging.getLogger(__name__)


@dataclass
class ContainerConfig:
    """Configuration for a container."""
    name: str
    image: str
    port: int
    env_vars: dict


class ContainerClient:
    """Client for communicating with FastAPI containers."""

    def __init__(self, config: ContainerConfig):
        self.config = config
        self.base_url = f"http://localhost:{config.port}"
        self.ws_url = f"ws://localhost:{config.port}"
        self.container_id: Optional[str] = None

    def start_container(self) -> str:
        """Start the container and return container ID."""
        logger.info(f"Starting container: {self.config.name}")

        # Check if container already exists
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={self.config.name}", "--format", "{{.ID}}"],
            capture_output=True,
            text=True
        )

        if result.stdout.strip():
            # Container exists, remove it first
            container_id = result.stdout.strip()
            logger.info(f"Removing existing container: {container_id}")
            subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)

        # Build docker run command
        cmd = [
            "docker", "run",
            "-d",  # Detached mode
            "--name", self.config.name,
            "-p", f"{self.config.port}:{self.config.port}",
        ]

        # Add environment variables
        for key, value in self.config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Add image
        cmd.append(self.config.image)

        # Run container
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"Failed to start container: {result.stderr}")

        self.container_id = result.stdout.strip()
        logger.info(f"Container started: {self.container_id[:12]}")

        return self.container_id

    def wait_for_ready(self, timeout: int = 30) -> bool:
        """Wait for container API to be ready."""
        logger.info(f"Waiting for {self.config.name} API to be ready at {self.base_url}/health...")

        start_time = time.time()
        attempt = 0
        while time.time() - start_time < timeout:
            attempt += 1
            try:
                logger.debug(f"Health check attempt {attempt} to {self.base_url}/health")
                # Increase timeout and add retries for flaky connections
                response = httpx.get(
                    f"{self.base_url}/health",
                    timeout=httpx.Timeout(10.0, connect=5.0),  # 10s total, 5s connect
                    follow_redirects=True
                )
                logger.debug(f"Health check response: status={response.status_code}")
                if response.status_code == 200:
                    logger.info(f"{self.config.name} API is ready!")
                    return True
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
                logger.debug(f"Health check attempt {attempt} failed: {type(e).__name__}: {e}")
                time.sleep(2)  # Wait longer between retries
            except Exception as e:
                logger.error(f"Unexpected error during health check: {type(e).__name__}: {e}")
                time.sleep(2)

        logger.error(f"{self.config.name} API did not become ready within {timeout}s after {attempt} attempts")
        return False

    async def clone_repository(self, repo_url: str, branch_name: str) -> dict:
        """Clone repository and checkout branch in the container."""
        logger.info(f"Cloning repository in {self.config.name}: {repo_url}")

        clone_data = {
            "repo_url": repo_url,
            "branch_name": branch_name,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:  # Longer timeout for cloning
            response = await client.post(
                f"{self.base_url}/clone",
                json=clone_data
            )

            if response.status_code != 200:
                raise RuntimeError(f"Failed to clone repository: {response.text}")

            return response.json()

    async def start_task(self, task_data: dict) -> dict:
        """Start a task on the container."""
        logger.info(f"Starting task on {self.config.name}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/start",
                json=task_data
            )

            if response.status_code != 200:
                raise RuntimeError(f"Failed to start task: {response.text}")

            return response.json()

    async def get_status(self) -> dict:
        """Get current status from container."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/status")
            return response.json()

    async def get_logs(self, count: int = 100) -> list:
        """Get recent logs from container."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/logs?count={count}")
            data = response.json()
            return data.get("logs", [])

    async def stream_logs(self, callback):
        """Stream logs in real-time via WebSocket."""
        uri = f"{self.ws_url}/logs/stream"
        logger.info(f"Connecting to log stream: {uri}")

        try:
            async with websockets.connect(uri) as websocket:
                logger.info("Log stream connected")
                async for message in websocket:
                    log_entry = json.loads(message)
                    callback(log_entry)
        except websockets.exceptions.ConnectionClosed:
            logger.info("Log stream connection closed")
        except Exception as e:
            logger.error(f"Log stream error: {e}")

    async def wait_for_completion(self, poll_interval: float = 2.0, timeout: Optional[float] = None):
        """
        Wait for task to complete.

        Args:
            poll_interval: How often to check status (seconds)
            timeout: Maximum time to wait (seconds), None for no timeout

        Returns:
            Final status dict

        Raises:
            TimeoutError: If timeout is reached
            RuntimeError: If task fails
        """
        start_time = time.time()

        while True:
            status = await self.get_status()
            logger.debug(f"Container status: {status}")

            if status["status"] in ["success", "failed"]:
                logger.info(f"Container completed with status: {status['status']}")
                if status["status"] == "failed":
                    error_msg = status.get("error", "Unknown error")
                    raise RuntimeError(f"Task failed: {error_msg}")
                return status

            if timeout and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Task did not complete within {timeout}s")

            await asyncio.sleep(poll_interval)

    def stop_container(self):
        """Stop and remove the container."""
        if self.container_id:
            logger.info(f"Stopping container: {self.container_id[:12]}")
            subprocess.run(["docker", "stop", self.container_id], capture_output=True)
            subprocess.run(["docker", "rm", self.container_id], capture_output=True)
            self.container_id = None
