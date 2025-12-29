"""
Comprehensive tests for workflow state machine and pipeline execution.

Tests cover:
- Workflow step configuration
- State transitions (pending → active → completed/failed)
- Feedback loop iteration logic
- Skip if complete logic
- Phase status management
- Current step tracking
- Integration with task log writer
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import json

from tests.fixtures.complex_spec import (
    get_complex_spec,
    create_complex_spec_files,
    COMPLEX_SPEC_NAME
)
from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy
from apps.backend.core.isolation.base import ContainerRole, ContainerResult, FeedbackComment


class TestWorkflowConfiguration:
    """Test workflow configuration and step definitions."""

    def test_workflow_has_three_steps(self):
        """Test default workflow has coding, review, testing steps."""
        from apps.backend.core.isolation.workflow_config import get_workflow

        workflow = get_workflow()

        assert len(workflow) == 3
        assert workflow[0].name == "coding"
        assert workflow[1].name == "code_review"
        assert workflow[2].name == "testing"

    def test_workflow_step_roles(self):
        """Test workflow steps have correct container roles."""
        from apps.backend.core.isolation.workflow_config import get_workflow

        workflow = get_workflow()

        assert workflow[0].role == ContainerRole.DEVELOPER
        assert workflow[1].role == ContainerRole.EVALUATOR
        assert workflow[2].role == ContainerRole.QA

    def test_workflow_step_accepts_feedback(self):
        """Test only developer step accepts feedback."""
        from apps.backend.core.isolation.workflow_config import get_workflow

        workflow = get_workflow()

        assert workflow[0].accepts_feedback is True  # Developer
        assert workflow[1].accepts_feedback is False  # Evaluator
        assert workflow[2].accepts_feedback is False  # QA

    def test_get_step_by_role(self):
        """Test retrieving workflow step by role."""
        from apps.backend.core.isolation.workflow_config import get_step_by_role

        dev_step = get_step_by_role(ContainerRole.DEVELOPER)
        assert dev_step is not None
        assert dev_step.name == "coding"

    def test_get_step_by_phase(self):
        """Test retrieving workflow step by phase name."""
        from apps.backend.core.isolation.workflow_config import get_step_by_phase

        coding_step = get_step_by_phase("coding")
        assert coding_step is not None
        assert coding_step.role == ContainerRole.DEVELOPER


@pytest.mark.asyncio
class TestWorkflowStateTransitions:
    """Test workflow state machine transitions."""

    async def test_successful_pipeline_all_steps_pass(self, docker_strategy, tmp_path):
        """Test pipeline when all steps pass on first iteration."""
        # Create spec files
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        # Mock orchestrator to return success for all steps
        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=[
                ContainerResult(ContainerRole.DEVELOPER, True, 0, "Success"),
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Tests passed"),
            ])

            result = await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is True
            # Verify all three containers were run
            assert mock_orch._run_container_http.call_count == 3

    async def test_pipeline_fails_after_max_iterations(self, docker_strategy, tmp_path):
        """Test pipeline fails after max feedback iterations."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        # Mock orchestrator to always fail developer step
        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(return_value=
                ContainerResult(
                    ContainerRole.DEVELOPER,
                    False,
                    1,
                    "Failed",
                    comments=[FeedbackComment(ContainerRole.EVALUATOR, "Fix this")]
                )
            )

            result = await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is False
            # Should try max_feedback_iterations times (3)
            assert mock_orch._run_container_http.call_count == 3

    async def test_pipeline_retries_on_evaluator_rejection(self, docker_strategy, tmp_path):
        """Test pipeline retries when evaluator rejects code."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        call_count = 0

        async def mock_run_container(role, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First: developer succeeds
                return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Done")
            elif call_count == 2:
                # Then: evaluator rejects
                return ContainerResult(
                    ContainerRole.EVALUATOR,
                    False,
                    1,
                    "Rejected",
                    comments=[FeedbackComment(ContainerRole.EVALUATOR, "Code quality issues")]
                )
            elif call_count == 3:
                # Retry: developer fixes issues
                return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Fixed")
            elif call_count == 4:
                # Retry: evaluator approves
                return ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved")
            else:
                # Finally: QA passes
                return ContainerResult(ContainerRole.QA, True, 0, "Tests passed")

        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=mock_run_container)

            result = await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is True
            # Should run: dev, eval(fail), dev(retry), eval(pass), qa
            assert call_count == 5


@pytest.mark.asyncio
class TestSkipIfComplete:
    """Test skip_if_complete logic."""

    async def test_skip_completed_phases(self, docker_strategy, tmp_path):
        """Test phases marked as completed are skipped."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        # Mark coding phase as complete
        from apps.backend.core.task_log_writer import TaskLogWriter
        spec_dir = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME
        log_writer = TaskLogWriter(spec_dir)
        log_writer.mark_phase_complete("coding", success=True)

        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=[
                # Coding skipped, start with evaluator
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Tests passed"),
            ])

            result = await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            assert result is True
            # Should only run evaluator and QA (coding was skipped)
            assert mock_orch._run_container_http.call_count == 2


@pytest.mark.asyncio
class TestFeedbackAccumulation:
    """Test feedback comment accumulation across iterations."""

    async def test_feedback_accumulates_across_retries(self, docker_strategy, tmp_path):
        """Test feedback comments accumulate across iterations."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        iteration_count = 0
        feedback_received = []

        async def mock_run_container(role, feedback_comments=None, **kwargs):
            nonlocal iteration_count, feedback_received

            if feedback_comments:
                feedback_received.append(json.loads(feedback_comments))

            if role == ContainerRole.DEVELOPER:
                iteration_count += 1
                if iteration_count == 1:
                    return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Done")
                elif iteration_count == 2:
                    return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Fixed")
                else:
                    return ContainerResult(ContainerRole.DEVELOPER, True, 0, "Final")

            elif role == ContainerRole.EVALUATOR:
                if iteration_count == 1:
                    return ContainerResult(
                        ContainerRole.EVALUATOR,
                        False,
                        1,
                        "Issues",
                        comments=[FeedbackComment(ContainerRole.EVALUATOR, "Fix issue 1")]
                    )
                else:
                    return ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved")

            else:  # QA
                return ContainerResult(ContainerRole.QA, True, 0, "Passed")

        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=mock_run_container)

            await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            # Verify feedback was sent to developer on retry
            assert len(feedback_received) > 0
            assert any("Fix issue 1" in str(fb) for fb in feedback_received)


@pytest.mark.asyncio
class TestStatusCallbacks:
    """Test status change callbacks during pipeline execution."""

    async def test_status_callback_called_for_each_step(self, docker_strategy, tmp_path):
        """Test status callback is called for each workflow step."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        status_changes = []

        def on_status_change(spec_name, status, message):
            status_changes.append((spec_name, status, message))

        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=[
                ContainerResult(ContainerRole.DEVELOPER, True, 0, "Success"),
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Passed"),
            ])

            await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"],
                on_status_change=on_status_change
            )

            # Should have status updates for: planning, coding, ai_review, ai_testing, ready_for_review
            assert len(status_changes) >= 4
            statuses = [s[1] for s in status_changes]
            assert "planning" in statuses
            assert "coding" in statuses
            assert "ready_for_review" in statuses


@pytest.mark.asyncio
class TestTaskLogIntegration:
    """Test integration with task log writer."""

    async def test_task_logs_updated_during_pipeline(self, docker_strategy, tmp_path):
        """Test task logs are updated as pipeline progresses."""
        create_complex_spec_files(tmp_path)
        spec = get_complex_spec()

        with patch.object(docker_strategy, '_orchestrator') as mock_orch:
            mock_orch._run_container_http = AsyncMock(side_effect=[
                ContainerResult(ContainerRole.DEVELOPER, True, 0, "Success"),
                ContainerResult(ContainerRole.EVALUATOR, True, 0, "Approved"),
                ContainerResult(ContainerRole.QA, True, 0, "Passed"),
            ])

            await docker_strategy.run_pipeline(
                spec_name=COMPLEX_SPEC_NAME,
                plan=spec["implementation_plan"]
            )

            # Verify task_logs.json was created and updated
            log_file = tmp_path / ".auto-claude" / "specs" / COMPLEX_SPEC_NAME / "task_logs.json"
            assert log_file.exists()

            logs = json.loads(log_file.read_text())
            assert logs["workflow_status"] == "ready_for_review"
            assert logs["phases"]["coding"]["status"] == "completed"
            assert logs["phases"]["validation"]["status"] == "completed"
            assert logs["phases"]["testing"]["status"] == "completed"


# Fixtures

@pytest.fixture
def docker_strategy(tmp_path):
    """Create a Docker strategy for testing."""
    return DockerIsolationStrategy(
        project_dir=tmp_path,
        base_branch="main",
        repo_url="https://github.com/test/repo.git",
        max_feedback_iterations=3
    )
