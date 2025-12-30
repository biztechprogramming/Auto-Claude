"""
Test Docker prompt formatting to ensure all prompts can be formatted without errors.

This test validates that all Docker-specific prompts can have their placeholders
replaced with actual values without causing format string errors.
"""

import pytest
import sys
from pathlib import Path

# Add the docker/api directory to the path so we can import context_loader
docker_api_path = Path(__file__).parent.parent / "apps" / "backend" / "docker" / "api"
sys.path.insert(0, str(docker_api_path))

from context_loader import safe_format_prompt


class TestDockerPromptFormatting:
    """Test that all Docker prompts can be formatted correctly."""

    @pytest.fixture
    def prompts_dir(self):
        """Get the prompts/docker directory."""
        # Assuming tests run from repo root
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

    def test_developer_prompt_formatting(self, prompts_dir, sample_values):
        """Test that developer.md can be formatted without errors."""
        developer_prompt_file = prompts_dir / "developer.md"
        assert developer_prompt_file.exists(), f"Developer prompt not found: {developer_prompt_file}"

        # Read the prompt
        prompt_template = developer_prompt_file.read_text(encoding="utf-8")

        # Try to format it using safe_format_prompt - this should not raise any errors
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{spec_content}" not in formatted

    def test_evaluator_prompt_formatting(self, prompts_dir, sample_values):
        """Test that evaluator.md can be formatted without errors."""
        evaluator_prompt_file = prompts_dir / "evaluator.md"
        assert evaluator_prompt_file.exists(), f"Evaluator prompt not found: {evaluator_prompt_file}"

        # Read the prompt
        prompt_template = evaluator_prompt_file.read_text(encoding="utf-8")

        # Try to format it using safe_format_prompt - this should not raise any errors
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{base_branch}" not in formatted
        assert "{spec_content}" not in formatted

    def test_qa_prompt_formatting(self, prompts_dir, sample_values):
        """Test that qa.md can be formatted without errors."""
        qa_prompt_file = prompts_dir / "qa.md"
        assert qa_prompt_file.exists(), f"QA prompt not found: {qa_prompt_file}"

        # Read the prompt
        prompt_template = qa_prompt_file.read_text(encoding="utf-8")

        # Try to format it using safe_format_prompt - this should not raise any errors
        formatted = safe_format_prompt(prompt_template, **sample_values)
        assert formatted is not None
        assert len(formatted) > 0
        # Verify placeholders were replaced
        assert "{branch_name}" not in formatted
        assert "{spec_content}" not in formatted

    def test_all_docker_prompts_exist(self, prompts_dir):
        """Verify all expected Docker prompts exist."""
        assert prompts_dir.exists(), f"Docker prompts directory not found: {prompts_dir}"

        expected_prompts = ["developer.md", "evaluator.md", "qa.md"]
        for prompt_name in expected_prompts:
            prompt_file = prompts_dir / prompt_name
            assert prompt_file.exists(), f"Expected prompt not found: {prompt_file}"

    def test_prompt_placeholders_documented(self, prompts_dir):
        """Verify all prompts use only documented placeholders."""
        expected_placeholders = {
            "developer.md": {"branch_name", "spec_content", "project_context", "memory_content", "feedback_comments"},
            "evaluator.md": {"branch_name", "base_branch", "spec_content", "project_context", "memory_content"},
            "qa.md": {"branch_name", "spec_content", "project_context", "memory_content"}
        }

        for prompt_name, expected_keys in expected_placeholders.items():
            prompt_file = prompts_dir / prompt_name
            if not prompt_file.exists():
                continue

            content = prompt_file.read_text(encoding="utf-8")

            # Extract all {placeholder} patterns (simple regex alternative)
            # Find all {xxx} patterns that are likely placeholders
            import re
            # Match {word} but not {{ or }} (escaped braces)
            pattern = r'\{([a-z_]+)\}'
            found_placeholders = set(re.findall(pattern, content))

            # Verify all found placeholders are expected
            for placeholder in found_placeholders:
                assert placeholder in expected_keys, \
                    f"{prompt_name} uses undocumented placeholder: {{{placeholder}}}"

    def test_no_unescaped_braces_in_code_blocks(self, prompts_dir):
        """
        Test that code blocks with curly braces are properly escaped.

        This is the critical test that would have caught the formatting error.
        Any literal { or } in the prompt that's NOT a placeholder should be escaped as {{ or }}.
        """
        for prompt_file in prompts_dir.glob("*.md"):
            content = prompt_file.read_text(encoding="utf-8")

            # Check if we can safely format with dummy values
            dummy_values = {
                "branch_name": "test",
                "base_branch": "main",
                "spec_content": "test",
                "project_context": "test",
                "memory_content": "test",
                "feedback_comments": "test"
            }

            try:
                # This should not raise ValueError due to unescaped braces
                content.format(**dummy_values)
            except ValueError as e:
                # If we get a ValueError, it means there are unescaped braces
                error_msg = str(e)
                pytest.fail(
                    f"{prompt_file.name} contains unescaped braces that break formatting.\n"
                    f"Error: {error_msg}\n\n"
                    f"Code blocks containing {{ or }} must escape them as {{{{ or }}}}.\n"
                    f"Example: grep 'pattern {{variable}}' should be grep 'pattern {{{{variable}}}}'"
                )
            except KeyError:
                # KeyError is OK - it means a placeholder is missing from dummy_values
                # We only care about ValueError (unescaped braces)
                pass


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
