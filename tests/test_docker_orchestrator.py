"""
Comprehensive tests for Docker orchestrator.

Tests cover:
- Orchestrator initialization
- Container naming
- Environment variable management
- Image building coordination
- Container lifecycle management
- HTTP-based container communication
- Log streaming and observation
- Error handling and timeouts
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock, call
import json

from apps.backend.core.isolation.orchestrator import DockerOrchestrator
from apps.backend.core.isolation.base import ContainerRole, ContainerResult, FeedbackComment


class TestOrchestratorInitialization:
    """Test orchestrator initialization."""

    def test_init_with_required_params(self, tmp_path):
        """Test initialization with required parameters."""
        orchestrator = DockerOrchestrator(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git",
            images={
                ContainerRole.DEVELOPER: "dev:latest",
                ContainerRole.EVALUATOR: "eval:latest",
                ContainerRole.QA: "qa:latest",
            }
        )

        assert orchestrator.project_dir == tmp_path
        assert orchestrator.base_branch == "main"
        assert orchestrator.repo_url == "https://github.com/test/repo.git"
        assert orchestrator.images[ContainerRole.DEVELOPER] == "dev:latest"
        assert orchestrator.memory_limit == "4g"
        assert orchestrator.cpu_shares == "1024"
        assert orchestrator.database_url is None

    def test_init_with_all_params(self, tmp_path):
        """Test initialization with all parameters."""
        orchestrator = DockerOrchestrator(
            project_dir=tmp_path,
            base_branch="develop",
            repo_url="https://gitlab.com/org/proj.git",
            images={
                ContainerRole.DEVELOPER: "custom-dev:v1",
                ContainerRole.EVALUATOR: "custom-eval:v1",
                ContainerRole.QA: "custom-qa:v1",
            },
            memory_limit="8g",
            cpu_shares="2048",
            database_url="postgresql://localhost/testdb"
        )

        assert orchestrator.base_branch == "develop"
        assert orchestrator.memory_limit == "8g"
        assert orchestrator.cpu_shares == "2048"
        assert orchestrator.database_url == "postgresql://localhost/testdb"

    def test_init_creates_image_builder(self, orchestrator):
        """Test that initialization creates image builder."""
        assert orchestrator.image_builder is not None

    def test_init_creates_container_manager(self, orchestrator):
        """Test that initialization creates container manager."""
        assert orchestrator.container_manager is not None
        assert orchestrator.container_manager.memory_limit == "4g"


class TestContainerNaming:
    """Test container name generation."""

    def test_get_container_name_developer(self, orchestrator):
        """Test container name for developer role."""
        name = orchestrator._get_container_name("test-spec", ContainerRole.DEVELOPER)
        assert name == "auto-claude-test-spec-developer"

    def test_get_container_name_evaluator(self, orchestrator):
        """Test container name for evaluator role."""
        name = orchestrator._get_container_name("test-spec", ContainerRole.EVALUATOR)
        assert name == "auto-claude-test-spec-evaluator"

    def test_get_container_name_qa(self, orchestrator):
        """Test container name for QA role."""
        name = orchestrator._get_container_name("test-spec", ContainerRole.QA)
        assert name == "auto-claude-test-spec-qa"

    def test_get_container_name_spec_with_numbers(self, orchestrator):
        """Test container name with spec containing numbers."""
        name = orchestrator._get_container_name("001-feature", ContainerRole.DEVELOPER)
        assert name == "auto-claude-001-feature-developer"


class TestEnvironmentVariables:
    """Test environment variable management."""

    def test_get_base_env_vars_minimal(self, orchestrator, monkeypatch):
        """Test base environment variables with minimal config."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "test-token-123")

        env = orchestrator._get_base_env_vars()

        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "test-token-123"
        assert env["REPO_URL"] == "https://github.com/test/repo.git"

    def test_get_base_env_vars_with_github_token(self, orchestrator, monkeypatch):
        """Test environment variables with GitHub token."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "claude-token")
        monkeypatch.setenv("GH_TOKEN", "github-token-456")

        env = orchestrator._get_base_env_vars()

        assert env["GH_TOKEN"] == "github-token-456"

    def test_get_base_env_vars_with_database(self, tmp_path, monkeypatch):
        """Test environment variables with database URL."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")

        orchestrator = DockerOrchestrator(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git",
            images={ContainerRole.DEVELOPER: "dev:latest"},
            database_url="postgresql://localhost/testdb"
        )

        env = orchestrator._get_base_env_vars()

        assert env["DATABASE_URL"] == "postgresql://localhost/testdb"
        assert env["DATABASE_READ_ONLY"] == "true"

    def test_get_base_env_vars_no_github_token(self, orchestrator, monkeypatch):
        """Test environment variables without GitHub token."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
        monkeypatch.delenv("GH_TOKEN", raising=False)

        env = orchestrator._get_base_env_vars()

        assert "GH_TOKEN" not in env or env["GH_TOKEN"] == ""


class TestTaskDescriptionExtraction:
    """Test task description extraction from plans."""

    def test_extract_task_description_from_feature(self, orchestrator):
        """Test extracting description from feature name."""
        plan = {"feature": "User authentication system"}

        desc = orchestrator._extract_task_description(plan, "001-auth")

        assert desc == "Implement User authentication system"

    def test_extract_task_description_from_first_subtask(self, orchestrator):
        """Test extracting description from first subtask."""
        plan = {
            "feature": "Dashboard",
            "phases": [
                {
                    "subtasks": [
                        {"description": "Create user profile endpoint with caching"},
                        {"description": "Add dashboard analytics"}
                    ]
                }
            ]
        }

        desc = orchestrator._extract_task_description(plan, "002-dash")

        assert desc == "Create user profile endpoint with caching"

    def test_extract_task_description_truncates_long_description(self, orchestrator):
        """Test description is truncated at 100 chars."""
        long_desc = "A" * 150
        plan = {
            "phases": [
                {"subtasks": [{"description": long_desc}]}
            ]
        }

        desc = orchestrator._extract_task_description(plan, "test")

        assert len(desc) == 100
        assert desc == "A" * 100

    def test_extract_task_description_first_sentence(self, orchestrator):
        """Test description is truncated at first sentence."""
        plan = {
            "phases": [
                {"subtasks": [{"description": "Create endpoint. Add tests. Deploy to prod."}]}
            ]
        }

        desc = orchestrator._extract_task_description(plan, "test")

        assert desc == "Create endpoint"

    def test_extract_task_description_fallback_to_spec_name(self, orchestrator):
        """Test fallback to spec name when no description."""
        plan = {"phases": []}

        desc = orchestrator._extract_task_description(plan, "my-feature")

        assert desc == "Implement my-feature"


class TestImageBuilding:
    """Test image building coordination."""

    def test_build_images_delegates_to_builder(self, orchestrator):
        """Test that build_images delegates to image builder."""
        # Mock the build_all_images method on the actual instance attribute
        orchestrator.image_builder.build_all_images = Mock()

        orchestrator.build_images(force=False)

        orchestrator.image_builder.build_all_images.assert_called_once_with(
            images=orchestrator.images,
            force=False
        )

    def test_build_images_with_force(self, orchestrator):
        """Test building images with force flag."""
        # Mock the build_all_images method on the actual instance attribute
        orchestrator.image_builder.build_all_images = Mock()

        orchestrator.build_images(force=True)

        orchestrator.image_builder.build_all_images.assert_called_once_with(
            images=orchestrator.images,
            force=True
        )


class TestContainerStatus:
    """Test container status retrieval."""

    def test_get_container_status_all_running(self, orchestrator):
        """Test getting status when all containers running."""
        # Mock the get_container_status method on the actual instance attribute
        orchestrator.container_manager.get_container_status = Mock(return_value={
            ContainerRole.DEVELOPER: "running",
            ContainerRole.EVALUATOR: "running",
            ContainerRole.QA: "running"
        })

        status = orchestrator.get_container_status("test-spec")

        assert status[ContainerRole.DEVELOPER] == "running"
        assert status[ContainerRole.EVALUATOR] == "running"
        assert status[ContainerRole.QA] == "running"

    def test_get_container_status_mixed(self, orchestrator):
        """Test getting status with mixed states."""
        # Mock the get_container_status method on the actual instance attribute
        orchestrator.container_manager.get_container_status = Mock(return_value={
            ContainerRole.DEVELOPER: "stopped",
            ContainerRole.EVALUATOR: "running",
            ContainerRole.QA: "not_found"
        })

        status = orchestrator.get_container_status("test-spec")

        assert status[ContainerRole.DEVELOPER] == "stopped"
        assert status[ContainerRole.EVALUATOR] == "running"
        assert status[ContainerRole.QA] == "not_found"


class TestContainerCleanup:
    """Test container cleanup."""

    def test_cleanup_containers_delegates(self, orchestrator):
        """Test cleanup delegates to container manager."""
        # Mock the cleanup_containers method on the actual instance attribute
        orchestrator.container_manager.cleanup_containers = Mock()

        orchestrator.cleanup_containers("test-spec")

        orchestrator.container_manager.cleanup_containers.assert_called_once_with("test-spec")


class TestRunContainerHTTP:
    """Test HTTP-based container execution."""

    def _mock_workflow_step(self, role: ContainerRole):
        """Helper to create a mock workflow step for a given role."""
        from apps.backend.core.isolation.workflow_config import WorkflowStep

        # Map roles to their workflow steps
        step_configs = {
            ContainerRole.DEVELOPER: {
                "name": "coding",
                "log_phase": "coding",
                "port": 8001,
                "description": "Implement code changes",
                "prompt_file": "coder.md",
                "kanban_status": "coding",
            },
            ContainerRole.EVALUATOR: {
                "name": "code_review",
                "log_phase": "validation",
                "port": 8002,
                "description": "Review code quality",
                "prompt_file": "qa_reviewer.md",
                "kanban_status": "ai_review",
            },
            ContainerRole.QA: {
                "name": "testing",
                "log_phase": "testing",
                "port": 8003,
                "description": "Run automated tests",
                "prompt_file": "qa_reviewer.md",
                "kanban_status": "ai_testing",
            },
        }

        config = step_configs[role]
        return WorkflowStep(
            name=config["name"],
            role=role,
            log_phase=config["log_phase"],
            port=config["port"],
            description=config["description"],
            prompt_file=config["prompt_file"],
            skip_if_complete=True,
            accepts_feedback=(role == ContainerRole.DEVELOPER),
            kanban_status=config["kanban_status"],
            task_template=f"{config['description']} for {{spec_name}}"
        )

    @pytest.mark.asyncio
    async def test_run_container_http_success(self, orchestrator, tmp_path, monkeypatch):
        """Test successful container execution via HTTP."""
        # Create spec directory and files
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        spec_file = spec_dir / "spec.md"
        spec_file.write_text("Test spec content", encoding="utf-8")

        # Mock workflow_config to return a valid step
        mock_step = self._mock_workflow_step(ContainerRole.DEVELOPER)
        with patch('core.isolation.workflow_config.get_step_by_role', return_value=mock_step):
            # Mock ContainerClient
            with patch('apps.backend.core.isolation.orchestrator.ContainerClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                # Mock client methods
                mock_client.start_container = Mock(return_value="container-123")
                mock_client.wait_for_ready = Mock(return_value=True)
                mock_client.clone_repository = AsyncMock()
                mock_client.start_task = AsyncMock()
                mock_client.wait_for_completion = AsyncMock(return_value={"status": "success"})
                mock_client.get_logs = AsyncMock(return_value=[
                    {"level": "INFO", "message": "Task started"},
                    {"level": "INFO", "message": "Task completed"}
                ])

                # Mock subprocess for log streaming
                with patch('subprocess.Popen') as mock_popen:
                    mock_process = MagicMock()
                    mock_process.stdout = iter(["Log line 1\n", "Log line 2\n"])
                    mock_process.pid = 12345
                    mock_popen.return_value = mock_process

                    result = await orchestrator._run_container_http(
                        role=ContainerRole.DEVELOPER,
                        spec_name="test-spec",
                        branch_name="auto-claude/test-spec",
                        spec_content="Test spec",
                        feedback_comments=None
                    )

                    assert result.success is True
                    assert result.role == ContainerRole.DEVELOPER
                    assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_run_container_http_api_not_ready(self, orchestrator, tmp_path):
        """Test container execution when API doesn't become ready."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # Mock workflow_config
        mock_step = self._mock_workflow_step(ContainerRole.DEVELOPER)
        with patch('core.isolation.workflow_config.get_step_by_role', return_value=mock_step):
            with patch('apps.backend.core.isolation.orchestrator.ContainerClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                mock_client.start_container = Mock(return_value="container-123")
                mock_client.wait_for_ready = Mock(return_value=False)  # Timeout
                mock_client.get_logs = AsyncMock(return_value=[])

                with patch('subprocess.Popen') as mock_popen:
                    mock_process = MagicMock()
                    mock_process.stdout = iter([])
                    mock_popen.return_value = mock_process

                    result = await orchestrator._run_container_http(
                        role=ContainerRole.DEVELOPER,
                        spec_name="test-spec",
                        branch_name="auto-claude/test-spec",
                        spec_content="Test",
                        feedback_comments=None
                    )

                    # The implementation returns a failure result instead of raising
                    assert result.success is False
                    assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_container_http_task_timeout(self, orchestrator, tmp_path):
        """Test container execution with task timeout."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # Mock workflow_config
        mock_step = self._mock_workflow_step(ContainerRole.QA)
        with patch('core.isolation.workflow_config.get_step_by_role', return_value=mock_step):
            with patch('apps.backend.core.isolation.orchestrator.ContainerClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                mock_client.start_container = Mock(return_value="container-123")
                mock_client.wait_for_ready = Mock(return_value=True)
                mock_client.clone_repository = AsyncMock()
                mock_client.start_task = AsyncMock()
                mock_client.wait_for_completion = AsyncMock(side_effect=TimeoutError("Timeout"))
                mock_client.get_logs = AsyncMock(return_value=[])

                with patch('subprocess.Popen') as mock_popen:
                    mock_process = MagicMock()
                    mock_process.stdout = iter([])
                    mock_popen.return_value = mock_process

                    result = await orchestrator._run_container_http(
                        role=ContainerRole.QA,
                        spec_name="test-spec",
                        branch_name="auto-claude/test-spec",
                        spec_content="Test",
                        feedback_comments=None
                    )

                    assert result.success is False
                    assert result.exit_code == 124  # Timeout exit code

    @pytest.mark.asyncio
    async def test_run_container_http_task_fails(self, orchestrator, tmp_path):
        """Test container execution when task fails."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        # Mock workflow_config
        mock_step = self._mock_workflow_step(ContainerRole.QA)
        with patch('core.isolation.workflow_config.get_step_by_role', return_value=mock_step):
            with patch('apps.backend.core.isolation.orchestrator.ContainerClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                mock_client.start_container = Mock(return_value="container-123")
                mock_client.wait_for_ready = Mock(return_value=True)
                mock_client.clone_repository = AsyncMock()
                mock_client.start_task = AsyncMock()
                mock_client.wait_for_completion = AsyncMock(
                    side_effect=RuntimeError("Task failed: tests failed")
                )
                mock_client.get_logs = AsyncMock(return_value=[
                    {"level": "ERROR", "message": "Test suite failed"}
                ])

                with patch('subprocess.Popen') as mock_popen:
                    mock_process = MagicMock()
                    mock_process.stdout = iter([])
                    mock_popen.return_value = mock_process

                    result = await orchestrator._run_container_http(
                        role=ContainerRole.QA,
                        spec_name="test-spec",
                        branch_name="auto-claude/test-spec",
                        spec_content="Test",
                        feedback_comments=None
                    )

                    assert result.success is False
                    assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_container_http_with_feedback(self, orchestrator, tmp_path):
        """Test container execution with feedback comments."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("Test", encoding="utf-8")

        feedback_json = json.dumps([{
            "source": "evaluator",
            "message": "Fix this",
            "file_path": "test.py",
            "line_number": 10,
            "severity": "error"
        }])

        # Mock workflow_config
        mock_step = self._mock_workflow_step(ContainerRole.DEVELOPER)
        with patch('core.isolation.workflow_config.get_step_by_role', return_value=mock_step):
            with patch('apps.backend.core.isolation.orchestrator.ContainerClient') as mock_client_class:
                mock_client = MagicMock()
                mock_client_class.return_value = mock_client

                mock_client.start_container = Mock(return_value="container-123")
                mock_client.wait_for_ready = Mock(return_value=True)
                mock_client.clone_repository = AsyncMock()
                mock_client.start_task = AsyncMock()
                mock_client.wait_for_completion = AsyncMock(return_value={"status": "success"})
                mock_client.get_logs = AsyncMock(return_value=[])

                with patch('subprocess.Popen') as mock_popen:
                    mock_process = MagicMock()
                    mock_process.stdout = iter([])
                    mock_popen.return_value = mock_process

                    result = await orchestrator._run_container_http(
                        role=ContainerRole.DEVELOPER,
                        spec_name="test-spec",
                        branch_name="auto-claude/test-spec",
                        spec_content="Test",
                        feedback_comments=feedback_json
                    )

                    # Verify feedback was passed to start_task
                    call_args = mock_client.start_task.call_args
                    task_data = call_args[0][0]
                    assert task_data["feedback_comments"] == feedback_json


class TestSpecificContainerMethods:
    """Test methods for running specific container types."""

    @pytest.mark.asyncio
    async def test_run_developer_with_plan(self, orchestrator, tmp_path):
        """Test running developer container with plan."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("Full spec content", encoding="utf-8")

        plan = {
            "feature": "Test feature",
            "phases": [{"subtasks": [{"description": "Task 1"}]}]
        }

        feedback = [
            FeedbackComment(
                source=ContainerRole.EVALUATOR,
                message="Fix syntax error",
                file_path="main.py",
                line_number=42,
                severity="error"
            )
        ]

        with patch.object(orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ContainerResult(
                role=ContainerRole.DEVELOPER,
                success=True,
                exit_code=0,
                output="Success"
            )

            result = await orchestrator.run_developer(
                spec_name="test-spec",
                branch_name="auto-claude/test-spec",
                plan=plan,
                feedback_comments=feedback
            )

            assert result.success is True
            # Verify feedback was serialized
            call_args = mock_run.call_args
            assert call_args[1]["feedback_comments"] is not None

    @pytest.mark.asyncio
    async def test_run_evaluator(self, orchestrator, tmp_path):
        """Test running evaluator container."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("Spec content", encoding="utf-8")

        with patch.object(orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ContainerResult(
                role=ContainerRole.EVALUATOR,
                success=True,
                exit_code=0,
                output="Approved"
            )

            result = await orchestrator.run_evaluator(
                spec_name="test-spec",
                branch_name="auto-claude/test-spec",
                commit_sha="abc123"
            )

            assert result.success is True
            assert result.role == ContainerRole.EVALUATOR

    @pytest.mark.asyncio
    async def test_run_qa(self, orchestrator, tmp_path):
        """Test running QA container."""
        spec_dir = tmp_path / ".auto-claude" / "specs" / "test-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)
        (spec_dir / "spec.md").write_text("Spec content", encoding="utf-8")

        with patch.object(orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ContainerResult(
                role=ContainerRole.QA,
                success=True,
                exit_code=0,
                output="All tests passed"
            )

            result = await orchestrator.run_qa(
                spec_name="test-spec",
                branch_name="auto-claude/test-spec",
                commit_sha="def456"
            )

            assert result.success is True
            assert result.role == ContainerRole.QA


# Fixtures are now in conftest.py
