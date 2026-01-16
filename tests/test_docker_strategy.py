"""
Comprehensive tests for Docker isolation strategy.

Tests cover:
- Initialization and configuration
- Environment creation and management
- Repository URL detection
- Branch management
- Docker availability checks
- Integration with orchestrator
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import os

from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy
from apps.backend.core.isolation.base import ContainerRole, IsolationInfo


class TestDockerStrategyInitialization:
    """Test Docker strategy initialization and configuration."""

    def test_init_with_defaults(self, docker_git_repo):
        """Test initialization with default values."""
        strategy = DockerIsolationStrategy(
            project_dir=docker_git_repo,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        assert strategy.project_dir == docker_git_repo
        assert strategy.image_developer == "auto-claude-dev:latest"
        assert strategy.image_evaluator == "auto-claude-eval:latest"
        assert strategy.image_qa == "auto-claude-qa:latest"
        assert strategy.memory_limit == "4g"
        assert strategy.cpu_shares == "1024"
        assert strategy.max_feedback_iterations == 3

    def test_init_with_custom_values(self, docker_git_repo):
        """Test initialization with custom values."""
        strategy = DockerIsolationStrategy(
            project_dir=docker_git_repo,
            base_branch="develop",
            repo_url="https://github.com/test/repo.git",
            image_developer="custom-dev:v1",
            image_evaluator="custom-eval:v1",
            image_qa="custom-qa:v1",
            memory_limit="8g",
            cpu_shares="2048",
            max_feedback_iterations=5
        )

        assert strategy.base_branch == "develop"
        assert strategy.image_developer == "custom-dev:v1"
        assert strategy.image_evaluator == "custom-eval:v1"
        assert strategy.image_qa == "custom-qa:v1"
        assert strategy.memory_limit == "8g"
        assert strategy.cpu_shares == "2048"
        assert strategy.max_feedback_iterations == 5

    def test_init_with_env_vars(self, tmp_path, monkeypatch):
        """Test initialization with environment variables."""
        monkeypatch.setenv("DOCKER_IMAGE_DEVELOPER", "env-dev:latest")
        monkeypatch.setenv("DOCKER_IMAGE_EVALUATOR", "env-eval:latest")
        monkeypatch.setenv("DOCKER_IMAGE_QA", "env-qa:latest")
        monkeypatch.setenv("DOCKER_MEMORY_LIMIT", "6g")
        monkeypatch.setenv("DOCKER_CPU_SHARES", "1536")
        monkeypatch.setenv("REPO_URL", "https://github.com/test/repo.git")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")

        strategy = DockerIsolationStrategy(project_dir=tmp_path, base_branch="main")

        assert strategy.image_developer == "env-dev:latest"
        assert strategy.image_evaluator == "env-eval:latest"
        assert strategy.image_qa == "env-qa:latest"
        assert strategy.memory_limit == "6g"
        assert strategy.cpu_shares == "1536"
        assert strategy.repo_url == "https://github.com/test/repo.git"
        assert strategy.database_url == "postgresql://localhost/test"

    def test_init_explicit_overrides_env(self, docker_git_repo, monkeypatch):
        """Test that explicit parameters override environment variables."""
        monkeypatch.setenv("DOCKER_IMAGE_DEVELOPER", "env-dev:latest")
        monkeypatch.setenv("DOCKER_MEMORY_LIMIT", "6g")

        strategy = DockerIsolationStrategy(
            project_dir=docker_git_repo,
            base_branch="main",
            repo_url="https://github.com/test/repo.git",
            image_developer="explicit-dev:latest",
            memory_limit="8g"
        )

        assert strategy.image_developer == "explicit-dev:latest"
        assert strategy.memory_limit == "8g"


class TestRepoUrlDetection:
    """Test repository URL detection and conversion."""

    @patch('subprocess.run')
    def test_detect_https_url(self, mock_run, tmp_path):
        """Test detection of HTTPS repository URL."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="https://github.com/user/repo.git\n"
        )

        strategy = DockerIsolationStrategy(project_dir=tmp_path, base_branch="main")
        assert strategy.repo_url == "https://github.com/user/repo.git"

    @patch('subprocess.run')
    def test_detect_ssh_url_converts_to_https(self, mock_run, tmp_path):
        """Test SSH URL is converted to HTTPS."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="git@github.com:user/repo.git\n"
        )

        strategy = DockerIsolationStrategy(project_dir=tmp_path, base_branch="main")
        assert strategy.repo_url == "https://github.com/user/repo.git"

    @patch('subprocess.run')
    def test_detect_ssh_url_gitlab(self, mock_run, tmp_path):
        """Test SSH URL conversion for GitLab."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="git@gitlab.com:org/project.git\n"
        )

        strategy = DockerIsolationStrategy(project_dir=tmp_path, base_branch="main")
        assert strategy.repo_url == "https://gitlab.com/org/project.git"

    @patch('subprocess.run')
    def test_detect_repo_url_failure(self, mock_run, tmp_path):
        """Test repository URL detection failure."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        with pytest.raises(RuntimeError, match="Could not detect repository URL"):
            DockerIsolationStrategy(project_dir=tmp_path, base_branch="main")

    def test_explicit_repo_url_skips_detection(self, tmp_path):
        """Test explicit repo URL skips auto-detection."""
        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://explicit.com/repo.git"
        )

        assert strategy.repo_url == "https://explicit.com/repo.git"


class TestBranchDetection:
    """Test branch detection logic."""

    @patch('subprocess.run')
    def test_detect_current_branch(self, mock_run, docker_git_repo):
        """Test detection of current branch."""
        # Mock returns branch name when detecting
        mock_run.return_value = Mock(
            returncode=0,
            stdout="feature/test\n",
            text=True
        )

        strategy = DockerIsolationStrategy(
            project_dir=docker_git_repo,
            repo_url="https://github.com/test/repo.git"
            # Don't pass base_branch so it will be detected
        )

        assert strategy.base_branch == "feature/test"

    @patch('subprocess.run')
    def test_detect_branch_detached_head(self, mock_run, tmp_path):
        """Test branch detection on detached HEAD."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="HEAD\n"
        )

        with pytest.raises(RuntimeError, match="Could not detect current branch"):
            DockerIsolationStrategy(
                project_dir=tmp_path,
                repo_url="https://github.com/test/repo.git"
            )

    @patch('subprocess.run')
    def test_detect_branch_failure(self, mock_run, tmp_path):
        """Test branch detection failure."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        with pytest.raises(RuntimeError, match="Could not detect current branch"):
            DockerIsolationStrategy(
                project_dir=tmp_path,
                repo_url="https://github.com/test/repo.git"
            )

    def test_explicit_branch_skips_detection(self, tmp_path):
        """Test explicit branch skips auto-detection."""
        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="explicit-branch",
            repo_url="https://github.com/test/repo.git"
        )

        assert strategy.base_branch == "explicit-branch"


class TestDockerAvailability:
    """Test Docker availability checks."""

    @patch('subprocess.run')
    def test_docker_available(self, mock_run, docker_strategy):
        """Test Docker is detected as available."""
        mock_run.return_value = Mock(returncode=0)

        assert docker_strategy.is_docker_available() is True
        mock_run.assert_called_once_with(
            ["docker", "--version"],
            capture_output=True,
            check=True
        )

    @patch('subprocess.run')
    def test_docker_not_installed(self, mock_run, docker_strategy):
        """Test Docker not installed."""
        mock_run.side_effect = FileNotFoundError()

        assert docker_strategy.is_docker_available() is False

    @patch('subprocess.run')
    def test_docker_command_fails(self, mock_run, docker_strategy):
        """Test Docker command fails."""
        mock_run.side_effect = subprocess.CalledProcessError(1, ["docker"])

        assert docker_strategy.is_docker_available() is False


class TestSetup:
    """Test strategy setup."""

    @patch.object(DockerIsolationStrategy, 'is_docker_available')
    def test_setup_success(self, mock_docker_available, docker_strategy):
        """Test successful setup."""
        mock_docker_available.return_value = True
        # Mock the build_images method on the actual instance attribute
        docker_strategy._orchestrator.build_images = Mock()

        docker_strategy.setup()

        mock_docker_available.assert_called_once()
        docker_strategy._orchestrator.build_images.assert_called_once()

    @patch.object(DockerIsolationStrategy, 'is_docker_available')
    def test_setup_docker_not_available(self, mock_docker_available, docker_strategy):
        """Test setup fails when Docker not available."""
        mock_docker_available.return_value = False

        with pytest.raises(RuntimeError, match="Docker is not available"):
            docker_strategy.setup()


class TestEnvironmentManagement:
    """Test environment creation and management."""

    @patch('subprocess.run')
    def test_create_environment(self, mock_run, docker_strategy):
        """Test creating a new environment."""
        mock_run.return_value = Mock(returncode=0)

        env_info = docker_strategy.create_environment("test-spec")

        assert env_info.spec_name == "test-spec"
        assert env_info.branch_name == "auto-claude/test-spec"
        assert env_info.is_active is True
        assert env_info.working_dir == docker_strategy.project_dir

        # Verify git commands were called
        calls = mock_run.call_args_list
        assert any("git" in str(call) and "branch" in str(call) for call in calls)

    @patch('subprocess.run')
    def test_create_environment_deletes_existing_branch(self, mock_run, docker_strategy):
        """Test creating environment deletes existing branch first."""
        mock_run.return_value = Mock(returncode=0)

        docker_strategy.create_environment("test-spec")

        # Should call git branch -D first (to delete if exists)
        calls = mock_run.call_args_list
        delete_call = [c for c in calls if "-D" in str(c) and "auto-claude/test-spec" in str(c)]
        assert len(delete_call) > 0

    @patch('subprocess.run')
    def test_get_environment_exists(self, mock_run, docker_strategy):
        """Test getting existing environment."""
        mock_run.return_value = Mock(returncode=0)

        env_info = docker_strategy.get_environment("test-spec")

        assert env_info is not None
        assert env_info.spec_name == "test-spec"
        assert env_info.branch_name == "auto-claude/test-spec"

    @patch('subprocess.run')
    def test_get_environment_not_exists(self, mock_run, docker_strategy):
        """Test getting non-existent environment."""
        mock_run.return_value = Mock(returncode=1)

        env_info = docker_strategy.get_environment("test-spec")

        assert env_info is None

    @patch('subprocess.run')
    def test_get_or_create_environment_exists(self, mock_run, docker_strategy):
        """Test get_or_create when environment exists."""
        mock_run.return_value = Mock(returncode=0)

        env_info = docker_strategy.get_or_create_environment("test-spec")

        assert env_info is not None
        assert env_info.spec_name == "test-spec"

    @patch('subprocess.run')
    def test_get_or_create_environment_creates_new(self, mock_run, docker_strategy):
        """Test get_or_create creates new environment."""
        # First call (git rev-parse) fails - branch doesn't exist
        # Subsequent calls succeed - branch creation
        mock_run.side_effect = [
            Mock(returncode=1),  # rev-parse fails
            Mock(returncode=0),  # branch -D succeeds
            Mock(returncode=0),  # branch creation succeeds
        ]

        env_info = docker_strategy.get_or_create_environment("test-spec")

        assert env_info is not None
        assert env_info.spec_name == "test-spec"


class TestEnvironmentRemoval:
    """Test environment removal and cleanup."""

    def test_remove_environment_no_branch_cleanup(self, docker_strategy):
        """Test removing environment without cleaning up branch."""
        # Mock the cleanup_containers method on the actual instance attribute
        docker_strategy._orchestrator.cleanup_containers = Mock()

        docker_strategy.remove_environment("test-spec", cleanup_branch=False)

        docker_strategy._orchestrator.cleanup_containers.assert_called_once_with("test-spec")

    @patch('subprocess.run')
    def test_remove_environment_with_branch_cleanup(self, mock_run, docker_strategy):
        """Test removing environment with branch cleanup."""
        # Mock the cleanup_containers method on the actual instance attribute
        docker_strategy._orchestrator.cleanup_containers = Mock()
        mock_run.return_value = Mock(returncode=0)

        docker_strategy.remove_environment("test-spec", cleanup_branch=True)

        docker_strategy._orchestrator.cleanup_containers.assert_called_once_with("test-spec")
        # Should call git branch -D
        mock_run.assert_called()
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "branch" in args
        assert "-D" in args
        assert "auto-claude/test-spec" in args


class TestMergeChanges:
    """Test merging changes from spec branch."""

    @patch('subprocess.run')
    def test_merge_changes_success(self, mock_run, docker_strategy):
        """Test successful merge."""
        mock_run.return_value = Mock(returncode=0, stderr="")
        # Mock the cleanup_containers method on the actual instance attribute
        docker_strategy._orchestrator.cleanup_containers = Mock()

        result = docker_strategy.merge_changes("test-spec", delete_after=False)

        assert result is True
        docker_strategy._orchestrator.cleanup_containers.assert_called_once_with("test-spec")

    @patch('subprocess.run')
    def test_merge_changes_with_delete(self, mock_run, docker_strategy):
        """Test merge with delete_after=True."""
        mock_run.return_value = Mock(returncode=0, stderr="")
        # Mock the cleanup_containers method on the actual instance attribute
        docker_strategy._orchestrator.cleanup_containers = Mock()

        result = docker_strategy.merge_changes("test-spec", delete_after=True)

        assert result is True
        # Should cleanup containers and delete branch
        docker_strategy._orchestrator.cleanup_containers.assert_called()

    @patch('subprocess.run')
    def test_merge_changes_checkout_fails(self, mock_run, docker_strategy):
        """Test merge fails on checkout."""
        mock_run.return_value = Mock(returncode=1, stderr="checkout failed")

        result = docker_strategy.merge_changes("test-spec")

        assert result is False

    @patch('subprocess.run')
    def test_merge_changes_merge_fails(self, mock_run, docker_strategy):
        """Test merge fails on merge command."""
        # Checkout succeeds, merge fails, then merge --abort
        mock_run.side_effect = [
            Mock(returncode=0, stderr=""),  # checkout
            Mock(returncode=1, stderr="merge conflict"),  # merge
            Mock(returncode=0, stderr="")  # merge --abort
        ]

        result = docker_strategy.merge_changes("test-spec")

        assert result is False
        # Should call merge --abort
        calls = mock_run.call_args_list
        abort_call = [c for c in calls if "--abort" in str(c)]
        assert len(abort_call) > 0


class TestListEnvironments:
    """Test listing environments."""

    @patch('subprocess.run')
    def test_list_environments_multiple(self, mock_run, docker_strategy):
        """Test listing multiple environments."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="  auto-claude/spec-001\n  auto-claude/spec-002\n* auto-claude/spec-003\n"
        )

        environments = docker_strategy.list_environments()

        assert len(environments) == 3
        assert environments[0].spec_name == "spec-001"
        assert environments[1].spec_name == "spec-002"
        assert environments[2].spec_name == "spec-003"

    @patch('subprocess.run')
    def test_list_environments_empty(self, mock_run, docker_strategy):
        """Test listing with no environments."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        environments = docker_strategy.list_environments()

        assert len(environments) == 0

    @patch('subprocess.run')
    def test_list_environments_git_fails(self, mock_run, docker_strategy):
        """Test listing when git command fails."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        environments = docker_strategy.list_environments()

        assert len(environments) == 0


class TestGetChangedFiles:
    """Test getting changed files."""

    @patch('subprocess.run')
    def test_get_changed_files_multiple(self, mock_run, docker_strategy):
        """Test getting multiple changed files."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="M\tfile1.py\nA\tfile2.py\nD\tfile3.py\n"
        )

        files = docker_strategy.get_changed_files("test-spec")

        assert len(files) == 3
        assert files[0] == ("M", "file1.py")
        assert files[1] == ("A", "file2.py")
        assert files[2] == ("D", "file3.py")

    @patch('subprocess.run')
    def test_get_changed_files_empty(self, mock_run, docker_strategy):
        """Test getting changed files when none exist."""
        mock_run.return_value = Mock(returncode=0, stdout="")

        files = docker_strategy.get_changed_files("test-spec")

        assert len(files) == 0


class TestContainerStatus:
    """Test getting container status."""

    def test_get_container_status(self, docker_strategy):
        """Test getting container status."""
        # Mock the get_container_status method on the actual instance attribute
        docker_strategy._orchestrator.get_container_status = Mock(return_value={
            ContainerRole.DEVELOPER: "running",
            ContainerRole.EVALUATOR: "stopped",
            ContainerRole.QA: "not_found"
        })

        status = docker_strategy.get_container_status("test-spec")

        assert status["developer"] == "running"
        assert status["evaluator"] == "stopped"
        assert status["qa"] == "not_found"


# Fixtures are now in conftest.py
