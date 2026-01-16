"""
Comprehensive tests for container lifecycle management.

Tests cover:
- Container naming
- Container existence checks
- Container running state checks
- Starting containers with configuration
- Stopping containers
- Removing containers
- Cleanup operations
- Resource limits
"""

import pytest
import subprocess
from unittest.mock import Mock, patch, call

from apps.backend.core.isolation.docker.container_manager import (
    ContainerLifecycleManager,
    ContainerConfig
)
from apps.backend.core.isolation.base import ContainerRole


class TestContainerNaming:
    """Test container name generation."""

    def test_get_container_name_developer(self, manager):
        """Test name generation for developer container."""
        name = manager.get_container_name("spec-001", ContainerRole.DEVELOPER)
        assert name == "auto-claude-spec-001-developer"

    def test_get_container_name_evaluator(self, manager):
        """Test name generation for evaluator container."""
        name = manager.get_container_name("spec-001", ContainerRole.EVALUATOR)
        assert name == "auto-claude-spec-001-evaluator"

    def test_get_container_name_qa(self, manager):
        """Test name generation for QA container."""
        name = manager.get_container_name("spec-001", ContainerRole.QA)
        assert name == "auto-claude-spec-001-qa"

    def test_get_container_name_with_special_chars(self, manager):
        """Test name generation with special characters in spec name."""
        name = manager.get_container_name("feature/new-api", ContainerRole.DEVELOPER)
        # Note: Docker might sanitize this, but we test what our function returns
        assert "feature/new-api" in name
        assert "developer" in name


class TestContainerExistence:
    """Test container existence checks."""

    @patch('subprocess.run')
    def test_container_exists_true(self, mock_run, manager):
        """Test checking if container exists."""
        mock_run.return_value = Mock(returncode=0, stdout="container-id-123\n", text=True)

        exists = manager.container_exists("test-container")

        assert exists is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "docker" in args
        assert "ps" in args
        assert "-a" in args  # All containers (including stopped)

    @patch('subprocess.run')
    def test_container_exists_false(self, mock_run, manager):
        """Test container doesn't exist."""
        mock_run.return_value = Mock(returncode=0, stdout="", text=True)

        exists = manager.container_exists("test-container")

        assert exists is False

    @patch('subprocess.run')
    def test_container_exists_docker_error(self, mock_run, manager):
        """Test container existence check with Docker error."""
        mock_run.return_value = Mock(returncode=1, stdout="", text=True)

        exists = manager.container_exists("test-container")

        # Should return False on error (conservative approach)
        assert exists is False


class TestContainerRunningState:
    """Test container running state checks."""

    @patch('subprocess.run')
    def test_is_container_running_true(self, mock_run, manager):
        """Test container is running."""
        mock_run.return_value = Mock(returncode=0, stdout="container-id\n", text=True)

        running = manager.is_container_running("test-container")

        assert running is True
        # Verify it checks running containers only (no -a flag)
        args = mock_run.call_args[0][0]
        assert "-a" not in args

    @patch('subprocess.run')
    def test_is_container_running_false(self, mock_run, manager):
        """Test container is not running."""
        mock_run.return_value = Mock(returncode=0, stdout="", text=True)

        running = manager.is_container_running("test-container")

        assert running is False

    @patch('subprocess.run')
    def test_is_container_running_docker_error(self, mock_run, manager):
        """Test running check with Docker error."""
        mock_run.return_value = Mock(returncode=1, stdout="", text=True)

        running = manager.is_container_running("test-container")

        assert running is False


class TestGetContainerStatus:
    """Test getting status of all containers for a spec."""

    @patch('subprocess.run')
    def test_get_container_status_all_running(self, mock_run, manager):
        """Test status when all containers are running."""
        # All containers running
        mock_run.return_value = Mock(returncode=0, stdout="id\n", text=True)

        status = manager.get_container_status("test-spec")

        assert status[ContainerRole.DEVELOPER] == "running"
        assert status[ContainerRole.EVALUATOR] == "running"
        assert status[ContainerRole.QA] == "running"

    @patch.object(ContainerLifecycleManager, 'is_container_running')
    @patch.object(ContainerLifecycleManager, 'container_exists')
    def test_get_container_status_mixed(self, mock_exists, mock_running, manager):
        """Test status with mixed states."""
        # Define behavior for each container
        def is_running(name):
            if "developer" in name:
                return True  # Developer is running
            return False  # Evaluator and QA are not running

        def exists(name):
            if "developer" in name:
                return True  # Developer exists (and is running)
            if "evaluator" in name:
                return True  # Evaluator exists (but not running)
            return False  # QA doesn't exist

        mock_running.side_effect = is_running
        mock_exists.side_effect = exists

        status = manager.get_container_status("test-spec")

        assert status[ContainerRole.DEVELOPER] == "running"
        assert status[ContainerRole.EVALUATOR] == "stopped"
        assert status[ContainerRole.QA] == "not_found"

    @patch('subprocess.run')
    def test_get_container_status_all_not_found(self, mock_run, manager):
        """Test status when no containers exist."""
        mock_run.return_value = Mock(returncode=0, stdout="", text=True)

        status = manager.get_container_status("test-spec")

        assert status[ContainerRole.DEVELOPER] == "not_found"
        assert status[ContainerRole.EVALUATOR] == "not_found"
        assert status[ContainerRole.QA] == "not_found"


class TestStopContainer:
    """Test stopping containers."""

    @patch.object(ContainerLifecycleManager, 'is_container_running')
    @patch('subprocess.run')
    def test_stop_container_running(self, mock_run, mock_is_running, manager):
        """Test stopping a running container."""
        mock_is_running.return_value = True
        mock_run.return_value = Mock(returncode=0)

        manager.stop_container("test-container")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["docker", "stop", "test-container"]

    @patch.object(ContainerLifecycleManager, 'is_container_running')
    @patch('subprocess.run')
    def test_stop_container_not_running(self, mock_run, mock_is_running, manager):
        """Test stopping a container that's not running."""
        mock_is_running.return_value = False

        manager.stop_container("test-container")

        # Should not call docker stop
        mock_run.assert_not_called()


class TestRemoveContainer:
    """Test removing containers."""

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_remove_container_exists(self, mock_run, mock_exists, manager):
        """Test removing an existing container."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0)

        manager.remove_container("test-container")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["docker", "rm", "test-container"]

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_remove_container_not_exists(self, mock_run, mock_exists, manager):
        """Test removing a non-existent container."""
        mock_exists.return_value = False

        manager.remove_container("test-container")

        # Should not call docker rm
        mock_run.assert_not_called()


class TestCleanupOperations:
    """Test cleanup operations."""

    @patch.object(ContainerLifecycleManager, 'stop_container')
    @patch.object(ContainerLifecycleManager, 'remove_container')
    def test_cleanup_container(self, mock_remove, mock_stop, manager):
        """Test cleaning up a single container."""
        manager.cleanup_container("test-container")

        mock_stop.assert_called_once_with("test-container")
        mock_remove.assert_called_once_with("test-container")

    @patch.object(ContainerLifecycleManager, 'cleanup_container')
    def test_cleanup_containers_all_roles(self, mock_cleanup, manager):
        """Test cleaning up all containers for a spec."""
        manager.cleanup_containers("test-spec")

        # Should cleanup all three container types
        assert mock_cleanup.call_count == 3
        calls = mock_cleanup.call_args_list

        # Extract container names from calls
        names = [call[0][0] for call in calls]
        assert "auto-claude-test-spec-developer" in names
        assert "auto-claude-test-spec-evaluator" in names
        assert "auto-claude-test-spec-qa" in names


class TestStartContainer:
    """Test starting containers with configuration."""

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch.object(ContainerLifecycleManager, 'cleanup_container')
    @patch('subprocess.run')
    def test_start_container_success(self, mock_run, mock_cleanup, mock_exists, manager):
        """Test successfully starting a container."""
        mock_exists.return_value = False
        mock_run.return_value = Mock(returncode=0, stdout="container-id-123\n", text=True)

        config = ContainerConfig(
            name="test-container",
            image="test:latest",
            port=8001,
            env_vars={"KEY": "value"},
            memory_limit="4g",
            cpu_shares="1024",
            pids_limit="256"
        )

        container_id = manager.start_container(config)

        assert container_id == "container-id-123"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]

        # Verify docker run command structure
        assert args[0:2] == ["docker", "run"]
        assert "-d" in args  # Detached mode
        assert "--name" in args
        assert "test-container" in args
        assert "-p" in args
        assert "8001:8001" in args
        assert "--memory" in args
        assert "4g" in args
        assert "--cpu-shares" in args
        assert "1024" in args
        assert "test:latest" in args

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch.object(ContainerLifecycleManager, 'cleanup_container')
    @patch('subprocess.run')
    def test_start_container_with_env_vars(self, mock_run, mock_cleanup, mock_exists, manager):
        """Test starting container with environment variables."""
        mock_exists.return_value = False
        mock_run.return_value = Mock(returncode=0, stdout="id\n", text=True)

        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={
                "CLAUDE_TOKEN": "token-123",
                "REPO_URL": "https://github.com/test/repo.git",
                "DATABASE_URL": "postgresql://localhost/test"
            }
        )

        manager.start_container(config)

        args = mock_run.call_args[0][0]
        # Verify environment variables are passed
        assert "-e" in args
        env_args = [args[i+1] for i, arg in enumerate(args) if arg == "-e"]
        assert "CLAUDE_TOKEN=token-123" in env_args
        assert "REPO_URL=https://github.com/test/repo.git" in env_args

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch.object(ContainerLifecycleManager, 'cleanup_container')
    @patch('subprocess.run')
    def test_start_container_removes_existing(self, mock_run, mock_cleanup, mock_exists, manager):
        """Test starting container removes existing one first."""
        mock_exists.return_value = True  # Container exists
        mock_run.return_value = Mock(returncode=0, stdout="id\n", text=True)

        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={}
        )

        manager.start_container(config)

        # Should cleanup existing container first
        mock_cleanup.assert_called_once_with("test")

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_start_container_with_additional_args(self, mock_run, mock_exists, manager):
        """Test starting container with additional Docker arguments."""
        mock_exists.return_value = False
        mock_run.return_value = Mock(returncode=0, stdout="id\n", text=True)

        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={}
        )

        additional_args = ["--network", "host", "--privileged"]

        manager.start_container(config, additional_docker_args=additional_args)

        args = mock_run.call_args[0][0]
        assert "--network" in args
        assert "host" in args
        assert "--privileged" in args

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_start_container_failure(self, mock_run, mock_exists, manager):
        """Test container start failure."""
        mock_exists.return_value = False
        mock_run.return_value = Mock(
            returncode=1,
            stderr="Error: image not found",
            text=True
        )

        config = ContainerConfig(
            name="test",
            image="nonexistent:latest",
            port=8001,
            env_vars={}
        )

        with pytest.raises(RuntimeError, match="Failed to start container"):
            manager.start_container(config)


class TestResourceLimits:
    """Test resource limit configuration."""

    def test_init_with_default_limits(self):
        """Test initialization with default resource limits."""
        manager = ContainerLifecycleManager()

        assert manager.memory_limit == "4g"
        assert manager.cpu_shares == "1024"

    def test_init_with_custom_limits(self):
        """Test initialization with custom resource limits."""
        manager = ContainerLifecycleManager(
            memory_limit="8g",
            cpu_shares="2048"
        )

        assert manager.memory_limit == "8g"
        assert manager.cpu_shares == "2048"

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_start_container_applies_resource_limits(self, mock_run, mock_exists):
        """Test that resource limits are applied when starting container."""
        mock_exists.return_value = False
        mock_run.return_value = Mock(returncode=0, stdout="id\n", text=True)

        manager = ContainerLifecycleManager(
            memory_limit="8g",
            cpu_shares="2048"
        )

        config = ContainerConfig(
            name="test",
            image="test:latest",
            port=8001,
            env_vars={},
            memory_limit="8g",
            cpu_shares="2048",
            pids_limit="512"
        )

        manager.start_container(config)

        args = mock_run.call_args[0][0]
        assert "--memory" in args
        assert "8g" in args
        assert "--cpu-shares" in args
        assert "2048" in args
        assert "--pids-limit" in args
        assert "512" in args


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('subprocess.run')
    def test_container_exists_empty_name(self, mock_run, manager):
        """Test checking existence of container with empty name."""
        mock_run.return_value = Mock(returncode=0, stdout="", text=True)

        exists = manager.container_exists("")

        assert exists is False

    @patch.object(ContainerLifecycleManager, 'is_container_running')
    @patch('subprocess.run')
    def test_stop_container_docker_fails(self, mock_run, mock_is_running, manager):
        """Test stopping container when Docker command fails."""
        mock_is_running.return_value = True
        mock_run.return_value = Mock(returncode=1, stderr="Error", text=True)

        # Should not raise - just log and continue
        manager.stop_container("test-container")

    @patch.object(ContainerLifecycleManager, 'container_exists')
    @patch('subprocess.run')
    def test_remove_container_docker_fails(self, mock_run, mock_exists, manager):
        """Test removing container when Docker command fails."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=1, stderr="Error", text=True)

        # Should not raise - just log and continue
        manager.remove_container("test-container")


# Fixtures

@pytest.fixture
def manager():
    """Create a container lifecycle manager for testing."""
    return ContainerLifecycleManager(
        memory_limit="4g",
        cpu_shares="1024"
    )
