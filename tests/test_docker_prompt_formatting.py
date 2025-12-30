"""
Test Docker prompt formatting to ensure all prompts can be formatted without errors.

This test validates that all Docker-specific prompts can have their placeholders
replaced with actual values without causing format string errors.
"""

import pytest
from pathlib import Path


class TestDockerPromptFormatting:
    """Test that all Docker prompts can be formatted correctly."""

    @pytest.fixture
    def prompts_dir(self):
        """Get the prompts/docker directory."""
        return Path(__file__).parent.parent / "apps" / "backend" / "prompts" / "docker"

    @pytest.fixture
    def sample_values(self):
        """Sample values for prompt placeholders."""
        return {
            "branch_name": "feature/test-feature",
            "base_branch": "main",
            "spec_content": "# Test Spec\n\nImplement a test feature.",
            "project_context": "## Project Context\n\nTest project context.",
            "memory_content": "## Memory\n\nTest memory content.",
            "feedback_comments": "Please fix the issue with error handling."
        }

    def test_developer_prompt_can_be_formatted(self, prompts_dir, sample_values):
        """Test that developer.md can be formatted without errors using the actual formatting method."""
        import sys
        docker_api_path = prompts_dir.parent.parent / "docker" / "api"
        sys.path.insert(0, str(docker_api_path))

        from context_loader import safe_format_prompt

        developer_prompt_file = prompts_dir / "developer.md"
        assert developer_prompt_file.exists(), f"Developer prompt not found: {developer_prompt_file}"

        prompt_template = developer_prompt_file.read_text(encoding="utf-8")

        # This should work with safe_format_prompt
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{spec_content}" not in formatted

    def test_evaluator_prompt_can_be_formatted(self, prompts_dir, sample_values):
        """Test that evaluator.md can be formatted without errors using the actual formatting method."""
        import sys
        docker_api_path = prompts_dir.parent.parent / "docker" / "api"
        sys.path.insert(0, str(docker_api_path))

        from context_loader import safe_format_prompt

        evaluator_prompt_file = prompts_dir / "evaluator.md"
        assert evaluator_prompt_file.exists(), f"Evaluator prompt not found: {evaluator_prompt_file}"

        prompt_template = evaluator_prompt_file.read_text(encoding="utf-8")

        # This should work with safe_format_prompt
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{base_branch}" not in formatted

    def test_qa_prompt_can_be_formatted(self, prompts_dir, sample_values):
        """Test that qa.md can be formatted without errors using the actual formatting method."""
        import sys
        docker_api_path = prompts_dir.parent.parent / "docker" / "api"
        sys.path.insert(0, str(docker_api_path))

        from context_loader import safe_format_prompt

        qa_prompt_file = prompts_dir / "qa.md"
        assert qa_prompt_file.exists(), f"QA prompt not found: {qa_prompt_file}"

        prompt_template = qa_prompt_file.read_text(encoding="utf-8")

        # This should work with safe_format_prompt
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{spec_content}" not in formatted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
