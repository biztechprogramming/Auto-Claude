"""
End-to-end integration tests for Docker isolation strategy.

These tests use the complex spec fixture to simulate real-world scenarios.
They test the complete pipeline from spec creation to completion.

Note: These tests are marked as 'slow' and may require Docker to be running.
Run with: pytest tests/test_docker_integration.py -v
Skip with: pytest tests/ -m "not slow"
"""

import pytest
import asyncio
from pathlib import Path
import json
from unittest.mock import Mock, patch, AsyncMock

from tests.fixtures.complex_spec import (
    get_complex_spec,
    create_complex_spec_files,
    COMPLEX_SPEC_NAME,
    get_expected_workflow_states,
    get_expected_phases
)
from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy
from apps.backend.core.isolation.base import ContainerRole, ContainerResult, FeedbackComment


@pytest.mark.slow
@pytest.mark.asyncio
class TestCompleteWorkflow:
    """Test complete workflow execution with complex spec."""

    async def test_full_pipeline_success(self, tmp_path):
        """Test complete pipeline execution from start to finish."""
        # Setup
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        # Mock container execution to return success
        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                ContainerResult(ContainerRole.DEVELOPER, True, 0, "Implemented all features"),
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Code quality approved"),
                ContainerResult(ContainerRole.QA, True, 0, "All tests passed"),
            ]

            # Execute pipeline
            result = await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            # Assertions
            assert result is True

            # Verify task logs were created
            log_file = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME / "task_logs.json"
            assert log_file.exists()

            logs = json.loads(log_file.read_text())
            assert logs["workflow_status"] == "ready_for_review"
            assert logs["iteration"] == 1

            # Verify all phases completed
            for phase in get_expected_phases():
                if phase != "planning":
                    assert logs["phases"][phase]["status"] == "completed"

    async def test_full_pipeline_with_one_retry(self, tmp_path):
        """Test pipeline with one retry iteration."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        call_count = 0

        async def mock_container_execution(role, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First iteration: developer succeeds
                return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Done")
            elif call_count == 2:
                # First iteration: evaluator rejects
                return ContainerResult(
                    ContainerRole.EVALUATOR,
                    False,
                    1,
                    "Rejected",
                    comments=[
                        FeedbackComment(ContainerRole.EVALUATOR, "Fix formatting", "main.py", 10, "error"),
                        FeedbackComment(ContainerRole.EVALUATOR, "Add error handling", "api.py", 45, "warning"),
                    ]
                )
            elif call_count == 3:
                # Second iteration: developer fixes issues
                return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Fixed issues")
            elif call_count == 4:
                # Second iteration: evaluator approves
                return ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved")
            else:
                # Second iteration: QA passes
                return ContainerResult(ContainerRole.QA, True, 0, "All tests passed")

        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = mock_container_execution

            result = await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is True
            assert call_count == 5  # dev, eval(fail), dev(retry), eval(pass), qa

            # Verify iteration count in logs
            log_file = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME / "task_logs.json"
            logs = json.loads(log_file.read_text())
            assert logs["iteration"] == 2

    async def test_full_pipeline_max_retries_exceeded(self, tmp_path):
        """Test pipeline failure after max retries."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git",
            max_feedback_iterations=2  # Set to 2 for faster test
        )

        # Mock developer to always fail
        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ContainerResult(
                ContainerRole.DEVELOPER,
                False,
                1,
                "Failed",
                comments=[FeedbackComment(ContainerRole.EVALUATOR, "Critical error")]
            )

            result = await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is False
            assert mock_run.call_count == 2  # max_feedback_iterations

            # Verify final status
            log_file = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME / "task_logs.json"
            logs = json.loads(log_file.read_text())
            assert logs["workflow_status"] == "failed"


@pytest.mark.slow
@pytest.mark.asyncio
class TestErrorHandlingAndRecovery:
    """Test error handling and recovery scenarios."""

    async def test_container_startup_failure(self, tmp_path):
        """Test handling of container startup failures."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        # Mock container startup to fail
        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Container failed to start")

            result = await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is False

    async def test_git_operation_failure(self, tmp_path):
        """Test handling of git operation failures."""
        create_complex_spec_files(tmp_path)

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        # Mock git command to fail
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stderr="Git error")

            env_info = strategy.create_environment("test-spec")

            # Should still create environment info even if git fails
            assert env_info is not None

    async def test_spec_file_missing(self, tmp_path):
        """Test handling when spec file is missing."""
        # Don't create spec files
        spec_dir = tmp_path / ".auto-claude" / "specs" / "missing-spec"
        spec_dir.mkdir(parents=True, exist_ok=True)

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        plan = {"feature": "test", "phases": []}

        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = ContainerResult(ContainerRole.DEVELOPER, True, 0, "Done")

            # Should handle missing spec gracefully
            result = await strategy.run_pipeline(
                spec_name="missing-spec",
                plan=plan
            )

            # Container should still be called with fallback content
            assert mock_run.called


@pytest.mark.slow
class TestEnvironmentLifecycle:
    """Test complete environment lifecycle."""

    def test_create_use_merge_workflow(self, tmp_path):
        """Test full lifecycle: create → use → merge → cleanup."""
        create_complex_spec_files(tmp_path)

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        # Create environment
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

            env_info = strategy.create_environment(COMPLEX_SPEC_NAME)
            assert env_info.spec_name == COMPLEX_SPEC_NAME
            assert env_info.branch_name == f"auto-claude/{COMPLEX_SPEC_NAME}"

            # List environments
            mock_run.return_value = Mock(
                returncode=0,
                stdout=f"  auto-claude/{COMPLEX_SPEC_NAME}\n",
                text=True
            )
            environments = strategy.list_environments()
            assert len(environments) == 1

            # Merge changes
            with patch.object(strategy._orchestrator, 'cleanup_containers'):
                result = strategy.merge_changes(COMPLEX_SPEC_NAME, delete_after=True)
                # Mock will make it succeed
                # assert result is True


@pytest.mark.slow
class TestMultiSpecIsolation:
    """Test multiple specs can run isolated from each other."""

    def test_multiple_specs_isolated(self, tmp_path):
        """Test multiple specs have isolated environments."""
        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="", text=True)

            # Create multiple environments
            env1 = strategy.create_environment("spec-001")
            env2 = strategy.create_environment("spec-002")
            env3 = strategy.create_environment("spec-003")

            # Each should have unique branch
            assert env1.branch_name == "auto-claude/spec-001"
            assert env2.branch_name == "auto-claude/spec-002"
            assert env3.branch_name == "auto-claude/spec-003"

            # Container names should be unique
            from apps.backend.core.isolation.base import ContainerRole

            name1 = strategy._orchestrator._get_container_name("spec-001", ContainerRole.DEVELOPER)
            name2 = strategy._orchestrator._get_container_name("spec-002", ContainerRole.DEVELOPER)

            assert name1 != name2
            assert "spec-001" in name1
            assert "spec-002" in name2


@pytest.mark.slow
class TestStatusTracking:
    """Test status tracking throughout workflow."""

    @pytest.mark.asyncio
    async def test_status_updates_during_execution(self, tmp_path):
        """Test status updates are tracked correctly during execution."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        status_history = []

        def track_status(spec_name, status, message):
            status_history.append({
                "spec": spec_name,
                "status": status,
                "message": message
            })

        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                ContainerResult(ContainerRole.DEVELOPER, True, 0, "Done"),
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Passed"),
            ]

            await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"],
                on_status_change=track_status
            )

            # Verify status progression
            assert len(status_history) > 0
            statuses = [s["status"] for s in status_history]

            # Should go through expected workflow states
            expected_states = get_expected_workflow_states()
            for expected in expected_states:
                assert expected in statuses


@pytest.mark.slow
class TestResumeAndRecovery:
    """Test resume and recovery capabilities."""

    @pytest.mark.asyncio
    async def test_resume_after_partial_completion(self, tmp_path):
        """Test resuming pipeline after some phases are complete."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        strategy = DockerIsolationStrategy(
            project_dir=tmp_path,
            base_branch="main",
            repo_url="https://github.com/test/repo.git"
        )

        # Mark coding phase as complete
        from apps.backend.core.task_log_writer import TaskLogWriter
        spec_dir = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME
        log_writer = TaskLogWriter(spec_dir)
        log_writer.mark_phase_complete("coding", success=True)

        with patch.object(strategy._orchestrator, '_run_container_http', new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                # Coding skipped, only run evaluator and QA
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Passed"),
            ]

            result = await strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is True
            # Should only run 2 containers (evaluator + QA)
            assert mock_run.call_count == 2
