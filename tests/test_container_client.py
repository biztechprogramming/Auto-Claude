"""
Tests for container client (HTTP communication with Docker containers).

Tests cover:
- Container startup
- Health checks
- Repository cloning
- Task execution
- Status polling
- Log retrieval
- Error handling
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import subprocess

from apps.backend.core.isolation.container_client import (
    ContainerClient,
    ContainerConfig
)


class TestContainerConfig:
    """Test container configuration dataclass."""

    def test_container_config_creation(self):
        """Test creating container configuration."""
        config = ContainerConfig(
            name="test-container",
            image="test:latest",
            port=8001,
            env_vars={"KEY": "value"}
        )

        assert config.name == "test-container"
        assert config.image == "test:latest"
        assert config.port == 8001
        assert config.env_vars["KEY"] == "value"


class TestContainerStartup:
    """Test container startup operations."""

    @patch('subprocess.run')
    def test_start_container_success(self, mock_run):
        """Test successfully starting a container."""
        # Mock container doesn't exist check
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", text=True),  # ps check (no existing)
            Mock(returncode=0, stdout="container-123\n", text=True)  # docker run
        ]

        config = ContainerConfig(
            name="test-container",
            image="test:latest",
            port=8001,
            env_vars={"TOKEN": "abc"}
        )

        client = ContainerClient(config)
        container_id = client.start_container()

        assert container_id == "container-123"
        assert client.container_id == "container-123"

    @patch('subprocess.run')
    def test_start_container_removes_existing(self, mock_run):
        """Test starting container removes existing one first."""
        # Mock existing container
        mock_run.side_effect = [
            Mock(returncode=0, stdout="old-container-id\n", text=True),  # ps check
            Mock(returncode=0),  # docker rm
            Mock(returncode=0, stdout="new-container-id\n", text=True)  # docker run
        ]

        config = ContainerConfig(
            name="test-container",
            image="test:latest",
            port=8001,
            env_vars={}
        )

        client = ContainerClient(config)
        container_id = client.start_container()

        assert container_id == "new-container-id"

        # Verify docker rm was called
        calls = mock_run.call_args_list
        rm_call = [c for c in calls if "rm" in str(c)]
        assert len(rm_call) > 0

    @patch('subprocess.run')
    def test_start_container_failure(self, mock_run):
        """Test container startup failure."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", text=True),  # ps check
            Mock(returncode=1, stderr="Image not found", text=True)  # docker run fails
        ]

        config = ContainerConfig(
            name="test-container",
            image="nonexistent:latest",
            port=8001,
            env_vars={}
        )

        client = ContainerClient(config)

        with pytest.raises(RuntimeError, match="Failed to start container"):
            client.start_container()

    @patch('subprocess.run')
    def test_start_container_with_env_vars(self, mock_run):
        """Test container starts with environment variables."""
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", text=True),
            Mock(returncode=0, stdout="id\n", text=True)
        ]

        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={
                "VAR1": "value1",
                "VAR2": "value2",
                "CLAUDE_TOKEN": "token-123"
            }
        )

        client = ContainerClient(config)
        client.start_container()

        # Check environment variables were passed
        run_call = mock_run.call_args_list[-1]
        args = run_call[0][0]

        assert "-e" in args
        # Extract -e arguments
        env_args = []
        for i, arg in enumerate(args):
            if arg == "-e" and i + 1 < len(args):
                env_args.append(args[i + 1])

        assert "VAR1=value1" in env_args
        assert "VAR2=value2" in env_args


class TestHealthChecks:
    """Test container health check operations."""

    @patch('httpx.get')
    def test_wait_for_ready_success(self, mock_get, container_client):
        """Test waiting for container to be ready."""
        mock_get.return_value = Mock(status_code=200)

        ready = container_client.wait_for_ready(timeout=5)

        assert ready is True

    @patch('httpx.get')
    def test_wait_for_ready_timeout(self, mock_get, container_client):
        """Test health check timeout."""
        mock_get.side_effect = Exception("Connection refused")

        ready = container_client.wait_for_ready(timeout=1)

        assert ready is False

    @patch('httpx.get')
    def test_wait_for_ready_retries(self, mock_get, container_client):
        """Test health check retries on failure."""
        # Fail first two times, succeed third time
        mock_get.side_effect = [
            Exception("Connection refused"),
            Exception("Connection refused"),
            Mock(status_code=200)
        ]

        ready = container_client.wait_for_ready(timeout=10)

        assert ready is True
        assert mock_get.call_count == 3


class TestRepositoryOperations:
    """Test repository cloning operations."""

    @pytest.mark.asyncio
    async def test_clone_repository_success(self, container_client):
        """Test successfully cloning repository."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock(status_code=200)
            mock_response.json.return_value = {"status": "success"}
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await container_client.clone_repository(
                "https://github.com/test/repo.git",
                "main"
            )

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_clone_repository_failure(self, container_client):
        """Test repository clone failure."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock(status_code=500, text="Clone failed")
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to clone repository"):
                await container_client.clone_repository(
                    "https://invalid.com/repo.git",
                    "main"
                )


class TestTaskExecution:
    """Test task execution operations."""

    @pytest.mark.asyncio
    async def test_start_task_success(self, container_client):
        """Test starting a task successfully."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock(status_code=200)
            mock_response.json.return_value = {"task_id": "task-123"}
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            task_data = {
                "repo_url": "https://github.com/test/repo.git",
                "branch_name": "main",
                "spec_content": "Test spec"
            }

            result = await container_client.start_task(task_data)

            assert result["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_start_task_failure(self, container_client):
        """Test task start failure."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock(status_code=400, text="Invalid task data")
            mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="Failed to start task"):
                await container_client.start_task({})


class TestStatusPolling:
    """Test status polling operations."""

    @pytest.mark.asyncio
    async def test_get_status_success(self, container_client):
        """Test getting container status."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock()
            mock_response.json.return_value = {"status": "running", "progress": 50}
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            status = await container_client.get_status()

            assert status["status"] == "running"
            assert status["progress"] == 50

    @pytest.mark.asyncio
    async def test_wait_for_completion_success(self, container_client):
        """Test waiting for task completion."""
        call_count = 0

        async def mock_get_status():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return {"status": "running"}
            return {"status": "success"}

        with patch.object(container_client, 'get_status', side_effect=mock_get_status):
            final_status = await container_client.wait_for_completion(poll_interval=0.01)

            assert final_status["status"] == "success"
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_wait_for_completion_failure(self, container_client):
        """Test waiting for failed task."""
        async def mock_get_status():
            return {"status": "failed", "error": "Tests failed"}

        with patch.object(container_client, 'get_status', side_effect=mock_get_status):
            with pytest.raises(RuntimeError, match="Task failed: Tests failed"):
                await container_client.wait_for_completion(poll_interval=0.01)

    @pytest.mark.asyncio
    async def test_wait_for_completion_timeout(self, container_client):
        """Test wait timeout."""
        async def mock_get_status():
            return {"status": "running"}

        with patch.object(container_client, 'get_status', side_effect=mock_get_status):
            with pytest.raises(TimeoutError):
                await container_client.wait_for_completion(poll_interval=0.01, timeout=0.05)


class TestLogRetrieval:
    """Test log retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_logs_success(self, container_client):
        """Test retrieving container logs."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock()
            mock_response.json.return_value = {
                "logs": [
                    {"level": "INFO", "message": "Task started"},
                    {"level": "INFO", "message": "Processing..."},
                    {"level": "INFO", "message": "Task completed"}
                ]
            }
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            logs = await container_client.get_logs(count=100)

            assert len(logs) == 3
            assert logs[0]["message"] == "Task started"
            assert logs[2]["message"] == "Task completed"

    @pytest.mark.asyncio
    async def test_get_logs_empty(self, container_client):
        """Test retrieving logs when none exist."""
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = MagicMock()
            mock_response = Mock()
            mock_response.json.return_value = {"logs": []}
            mock_client.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            logs = await container_client.get_logs()

            assert logs == []


class TestContainerCleanup:
    """Test container cleanup operations."""

    @patch('subprocess.run')
    def test_stop_container(self, mock_run):
        """Test stopping a container."""
        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={}
        )

        client = ContainerClient(config)
        client.container_id = "container-123"

        client.stop_container()

        # Verify docker stop and docker rm were called
        assert mock_run.call_count == 2
        calls = mock_run.call_args_list

        stop_call = calls[0][0][0]
        assert "docker" in stop_call
        assert "stop" in stop_call

        rm_call = calls[1][0][0]
        assert "docker" in rm_call
        assert "rm" in rm_call


# Fixtures

@pytest.fixture
def container_client():
    """Create a container client for testing."""
    config = ContainerConfig(
        name="test-container",
        image="test:latest",
        port=8001,
        env_vars={"TOKEN": "test-token"}
    )
    return ContainerClient(config)
