"""
Tests for build_commands.py Docker isolation integration.

Ensures that Docker isolation is properly invoked when ISOLATION_METHOD=docker,
and that undefined variables or programming errors don't cause fallback to worktree mode.

CRITICAL REGRESSION TEST: This test suite specifically guards against the bug where
'resolved_model' was used instead of 'model', causing Docker isolation to fail and
fall back to worktree mode silently.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os

# Add backend to path
backend_dir = Path(__file__).parent.parent / "apps" / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


@pytest.fixture
def mock_project_setup(tmp_path):
    """Create a mock project with spec directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    # Create .auto-claude/specs directory
    spec_dir = project_dir / ".auto-claude" / "specs" / "001-test-feature"
    spec_dir.mkdir(parents=True)

    # Create required spec files
    (spec_dir / "spec.md").write_text("# Test Feature\n\nTest spec content")
    (spec_dir / "implementation_plan.json").write_text('''{
        "feature": "test-feature",
        "subtasks": [
            {"id": "1", "description": "Task 1", "status": "pending"}
        ],
        "status": "human_review",
        "planStatus": "review"
    }''')

    # Create review approval file
    (spec_dir / "review_state.json").write_text('''{
        "approved": true,
        "approved_by": "test-user",
        "approved_at": "2024-01-01T00:00:00",
        "spec_checksum": "abc123"
    }''')

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "checkout", "-b", "main"], cwd=project_dir, capture_output=True)
    (project_dir / "README.md").write_text("# Test Project")
    subprocess.run(["git", "add", "."], cwd=project_dir, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=project_dir, capture_output=True)

    return {
        "project_dir": project_dir,
        "spec_dir": spec_dir,
    }


class TestDockerIsolationInvocation:
    """Test that Docker isolation is correctly invoked from build_commands."""

    def test_docker_isolation_invoked_when_enabled(self, mock_project_setup):
        """
        Test that when ISOLATION_METHOD=docker, the Docker isolation strategy
        is invoked and NOT the worktree mode.

        This test ensures that the bug with undefined 'resolved_model' doesn't recur.
        """
        from cli.build_commands import handle_build_command
        from core.isolation_adapter import get_isolation_strategy

        project_dir = mock_project_setup["project_dir"]
        spec_dir = mock_project_setup["spec_dir"]

        # Mock environment variable
        with patch.dict(os.environ, {"ISOLATION_METHOD": "docker"}):
            # Mock the isolation strategy
            mock_isolation = Mock()
            mock_isolation.setup = Mock()
            mock_isolation.run_pipeline = AsyncMock(return_value=True)

            # Mock get_isolation_strategy to return our mock
            with patch('cli.build_commands.get_isolation_strategy', return_value=mock_isolation) as mock_get_strategy:
                # Mock should_use_docker_isolation to return True
                with patch('cli.build_commands.should_use_docker_isolation', return_value=True):
                    # Mock print functions to avoid output
                    with patch('builtins.print'):
                        with patch('cli.utils.print_banner'):
                            with patch('cli.utils.validate_environment', return_value=True):
                                with patch('review.ReviewState.load') as mock_review:
                                    # Mock review state as approved
                                    mock_review_obj = Mock()
                                    mock_review_obj.is_approval_valid = Mock(return_value=True)
                                    mock_review_obj.approved = True
                                    mock_review_obj.approved_by = "test-user"
                                    mock_review.return_value = mock_review_obj

                                    with patch('workspace.get_existing_build_worktree', return_value=None):
                                        with patch('ui.StatusManager'):
                                            with patch('phase_config.get_phase_model', side_effect=lambda *args: 'claude-sonnet-4'):
                                                # Call the function
                                                handle_build_command(
                                                    project_dir=project_dir,
                                                    spec_dir=spec_dir,
                                                    model="claude-sonnet-4",
                                                    max_iterations=None,
                                                    verbose=False,
                                                    force_isolated=False,
                                                    force_direct=False,
                                                    auto_continue=False,
                                                    skip_qa=True,
                                                    force_bypass_approval=False,
                                                    base_branch="main",
                                                )

                # CRITICAL ASSERTION: Verify get_isolation_strategy was called with correct model parameter
                mock_get_strategy.assert_called_once()
                call_args = mock_get_strategy.call_args

                # Check that it was called with the model parameter (not undefined variable)
                assert call_args[1]["model"] == "claude-sonnet-4", \
                    "get_isolation_strategy should receive the model parameter, not undefined 'resolved_model'"

                # Verify Docker pipeline was invoked (not worktree mode)
                mock_isolation.setup.assert_called_once()
                mock_isolation.run_pipeline.assert_called_once()

    def test_docker_isolation_exception_fails_loudly(self, mock_project_setup):
        """
        Test that when Docker initialization fails, it EXITS with clear error message.

        CRITICAL UX: When user explicitly configures ISOLATION_METHOD=docker, they want
        it to FAIL LOUDLY if Docker isn't working, not silently fall back to worktree.
        Silent fallback wastes time and hides configuration problems.
        """
        from cli.build_commands import handle_build_command

        project_dir = mock_project_setup["project_dir"]
        spec_dir = mock_project_setup["spec_dir"]

        # Mock environment variable
        with patch.dict(os.environ, {"ISOLATION_METHOD": "docker"}):
            # Mock get_isolation_strategy to raise an exception (Docker not available)
            with patch('cli.build_commands.get_isolation_strategy', side_effect=RuntimeError("Docker not running")) as mock_get_strategy:
                with patch('cli.build_commands.should_use_docker_isolation', return_value=True):
                    with patch('builtins.print'):
                        with patch('cli.utils.print_banner'):
                            with patch('cli.utils.validate_environment', return_value=True):
                                with patch('review.ReviewState.load') as mock_review:
                                    mock_review_obj = Mock()
                                    mock_review_obj.is_approval_valid = Mock(return_value=True)
                                    mock_review_obj.approved = True
                                    mock_review.return_value = mock_review_obj

                                    with patch('workspace.get_existing_build_worktree', return_value=None):
                                        with patch('phase_config.get_phase_model', side_effect=lambda *args: 'claude-sonnet-4'):
                                            # Should exit with error
                                            with pytest.raises(SystemExit) as exc_info:
                                                handle_build_command(
                                                    project_dir=project_dir,
                                                    spec_dir=spec_dir,
                                                    model="claude-sonnet-4",
                                                    max_iterations=1,
                                                    verbose=False,
                                                    force_isolated=False,
                                                    force_direct=True,
                                                    auto_continue=False,
                                                    skip_qa=True,
                                                    force_bypass_approval=False,
                                                    base_branch="main",
                                                )

                        # Verify it exited with error code 1
                        assert exc_info.value.code == 1

                        # Verify Docker was attempted
                        mock_get_strategy.assert_called_once()

    def test_model_parameter_passed_correctly(self, mock_project_setup):
        """
        Regression test: Ensure the 'model' parameter is passed to get_isolation_strategy,
        not an undefined variable like 'resolved_model'.

        This is the specific bug that was fixed.
        """
        from cli.build_commands import handle_build_command

        project_dir = mock_project_setup["project_dir"]
        spec_dir = mock_project_setup["spec_dir"]

        test_model = "claude-opus-4"

        with patch.dict(os.environ, {"ISOLATION_METHOD": "docker"}):
            mock_isolation = Mock()
            mock_isolation.setup = Mock()
            mock_isolation.run_pipeline = AsyncMock(return_value=True)

            with patch('cli.build_commands.get_isolation_strategy', return_value=mock_isolation) as mock_get_strategy:
                with patch('cli.build_commands.should_use_docker_isolation', return_value=True):
                    with patch('builtins.print'):
                        with patch('cli.utils.print_banner'):
                            with patch('cli.utils.validate_environment', return_value=True):
                                with patch('review.ReviewState.load') as mock_review:
                                    mock_review_obj = Mock()
                                    mock_review_obj.is_approval_valid = Mock(return_value=True)
                                    mock_review_obj.approved = True
                                    mock_review.return_value = mock_review_obj

                                    with patch('workspace.get_existing_build_worktree', return_value=None):
                                        with patch('ui.StatusManager'):
                                            with patch('phase_config.get_phase_model', side_effect=lambda *args: test_model):
                                                handle_build_command(
                                                    project_dir=project_dir,
                                                    spec_dir=spec_dir,
                                                    model=test_model,
                                                    max_iterations=None,
                                                    verbose=False,
                                                    force_isolated=False,
                                                    force_direct=False,
                                                    auto_continue=False,
                                                    skip_qa=True,
                                                    force_bypass_approval=False,
                                                    base_branch="main",
                                                )

                # The key assertion: model parameter must be passed (not undefined)
                call_kwargs = mock_get_strategy.call_args[1]
                assert "model" in call_kwargs, "model parameter must be passed to get_isolation_strategy"
                assert call_kwargs["model"] == test_model, f"Expected model={test_model}, got {call_kwargs['model']}"


class TestWorktreeModeFallback:
    """Test that worktree mode is used when Docker is disabled."""

    def test_worktree_mode_when_docker_disabled(self, mock_project_setup):
        """Verify worktree mode is used when ISOLATION_METHOD != docker."""
        from cli.build_commands import handle_build_command

        project_dir = mock_project_setup["project_dir"]
        spec_dir = mock_project_setup["spec_dir"]

        # Explicitly set to worktree mode
        with patch.dict(os.environ, {"ISOLATION_METHOD": "worktree"}):
            with patch('cli.build_commands.should_use_docker_isolation', return_value=False):
                with patch('workspace.choose_workspace', return_value="direct"):
                    with patch('agent.run_autonomous_agent', new_callable=AsyncMock):
                        with patch('qa_loop.should_run_qa', return_value=False):
                            with patch('cli.build_commands.get_isolation_strategy') as mock_get_strategy:
                                with patch('builtins.print'):
                                    with patch('cli.utils.print_banner'):
                                        with patch('cli.utils.validate_environment', return_value=True):
                                            with patch('review.ReviewState.load') as mock_review:
                                                mock_review_obj = Mock()
                                                mock_review_obj.is_approval_valid = Mock(return_value=True)
                                                mock_review.return_value = mock_review_obj

                                                with patch('workspace.get_existing_build_worktree', return_value=None):
                                                    with patch('phase_config.get_phase_model', side_effect=lambda *args: 'claude-sonnet-4'):
                                                        # Use force_direct=True to avoid interactive workspace selection
                                                        handle_build_command(
                                                            project_dir=project_dir,
                                                            spec_dir=spec_dir,
                                                            model="claude-sonnet-4",
                                                            max_iterations=1,
                                                            verbose=False,
                                                            force_isolated=False,
                                                            force_direct=True,  # Force direct mode to avoid prompts
                                                            auto_continue=False,
                                                            skip_qa=True,
                                                            force_bypass_approval=False,
                                                            base_branch="main",
                                                        )

                                # Docker isolation should NOT be invoked
                                mock_get_strategy.assert_not_called()
