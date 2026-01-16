#!/usr/bin/env python3
"""
End-to-End Docker Integration Tests
====================================

CRITICAL: These tests validate that Docker containers ACTUALLY WORK:
- Containers build correctly with all dependencies
- Prompts execute and produce valid, working code
- Code evaluation correctly identifies issues
- Testing workflow validates functionality

These are REAL integration tests that:
- Require Docker installed and running
- Require CLAUDE_CODE_OAUTH_TOKEN environment variable
- Actually build and run containers
- Actually execute Claude API calls
- Validate real code generation, review, and testing

To run these tests:
    # Set OAuth token first
    export CLAUDE_CODE_OAUTH_TOKEN=your_token_here

    # Run all e2e tests (will take several minutes)
    pytest tests/test_docker_e2e.py -v -s

    # Run only container build tests (faster)
    pytest tests/test_docker_e2e.py::TestDockerContainerBuilds -v

    # Skip e2e tests entirely (for CI)
    export SKIP_DOCKER_E2E=1
    pytest tests/

IMPORTANT: These tests are expensive (API calls, Docker builds, time).
Run them sparingly and only when validating core Docker functionality.
"""

import json
import os
import subprocess
import pytest
from pathlib import Path
from unittest.mock import Mock

# Only skip if explicitly disabled via environment variable
if os.environ.get("SKIP_DOCKER_E2E") == "1":
    pytestmark = pytest.mark.skip(reason="Docker E2E tests disabled (SKIP_DOCKER_E2E=1)")


@pytest.fixture
def oauth_token():
    """Get OAuth token from environment."""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        pytest.skip("CLAUDE_CODE_OAUTH_TOKEN not set - cannot run E2E tests")
    return token


@pytest.fixture
def project_root():
    """
    Get the actual project root directory for E2E testing.

    E2E tests need to build Docker images from the real project structure,
    not a temp directory, since they need access to Dockerfiles and context.
    """
    # Find project root (where apps/backend exists)
    current = Path(__file__).parent.parent  # Go up from tests/ to project root
    return current


class TestDockerContainerBuilds:
    """
    Test that Docker containers build successfully.

    These tests validate:
    - Dockerfiles are syntactically correct
    - All required dependencies are available
    - Containers can be built without errors
    - Required tools are installed (git, python, node, etc.)
    """

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_developer_container_builds(self, real_git_repo, real_repo_url):
        """Test that developer container builds successfully."""
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        # Build developer image
        try:
            result = subprocess.run(
                [
                    "docker", "build",
                    "-f", "apps/backend/docker/Dockerfile.developer",
                    "-t", strategy.image_developer,
                    "apps/backend"
                ],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            assert result.returncode == 0, f"Developer container build failed:\n{result.stderr}"

            # Verify image exists
            check_result = subprocess.run(
                ["docker", "images", "-q", strategy.image_developer],
                capture_output=True,
                text=True
            )
            assert check_result.stdout.strip(), "Developer image not found after build"

        except subprocess.TimeoutExpired:
            pytest.fail("Developer container build timed out after 5 minutes")

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_evaluator_container_builds(self, real_git_repo, real_repo_url):
        """Test that evaluator container builds successfully."""
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        # Build evaluator image
        try:
            result = subprocess.run(
                [
                    "docker", "build",
                    "-f", "apps/backend/docker/Dockerfile.evaluator",
                    "-t", strategy.image_evaluator,
                    "apps/backend"
                ],
                capture_output=True,
                text=True,
                timeout=300
            )

            assert result.returncode == 0, f"Evaluator container build failed:\n{result.stderr}"

            # Verify image exists
            check_result = subprocess.run(
                ["docker", "images", "-q", strategy.image_evaluator],
                capture_output=True,
                text=True
            )
            assert check_result.stdout.strip(), "Evaluator image not found after build"

        except subprocess.TimeoutExpired:
            pytest.fail("Evaluator container build timed out after 5 minutes")

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_qa_container_builds(self, real_git_repo, real_repo_url):
        """Test that QA container builds successfully."""
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        # Build QA image
        try:
            result = subprocess.run(
                [
                    "docker", "build",
                    "-f", "apps/backend/docker/Dockerfile.qa",
                    "-t", strategy.image_qa,
                    "apps/backend"
                ],
                capture_output=True,
                text=True,
                timeout=300
            )

            assert result.returncode == 0, f"QA container build failed:\n{result.stderr}"

            # Verify image exists
            check_result = subprocess.run(
                ["docker", "images", "-q", strategy.image_qa],
                capture_output=True,
                text=True
            )
            assert check_result.stdout.strip(), "QA image not found after build"

        except subprocess.TimeoutExpired:
            pytest.fail("QA container build timed out after 5 minutes")


class TestContainerToolsAndDependencies:
    """
    Test that containers have all required tools installed.

    Validates that each container type has:
    - Git for repository operations
    - Python/Node for code execution
    - Claude SDK for API access
    - Other required dependencies
    """

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_developer_container_has_required_tools(self, real_git_repo, real_repo_url, oauth_token):
        """Test that developer container has all required development tools."""
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        # First ensure image is built
        strategy.setup()

        # Run container and check for tools
        commands_to_check = [
            ("git", ["git", "--version"]),
            ("python", ["python3", "--version"]),
            ("pip", ["pip3", "--version"]),
            ("node", ["node", "--version"]),
            ("npm", ["npm", "--version"]),
        ]

        for tool_name, command in commands_to_check:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    strategy.image_developer,
                    *command
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            assert result.returncode == 0, \
                f"Developer container missing {tool_name}:\n{result.stderr}"

    @pytest.mark.slow
    @pytest.mark.e2e
    def test_containers_have_claude_sdk(self, real_git_repo, real_repo_url, oauth_token):
        """Test that all containers have Claude SDK installed."""
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        strategy.setup()

        # Check each container type
        for image_name in [strategy.image_developer, strategy.image_evaluator, strategy.image_qa]:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    image_name,
                    "python3", "-c", "import claude_agent_sdk; print(claude_agent_sdk.__version__)"
                ],
                capture_output=True,
                text=True,
                timeout=30
            )

            assert result.returncode == 0, \
                f"Container {image_name} missing Claude SDK:\n{result.stderr}"
            assert result.stdout.strip(), \
                f"Container {image_name} has Claude SDK but version not detected"


class TestPromptExecution:
    """
    CRITICAL: Test that prompts actually execute and produce valid code.

    These tests validate the MOST IMPORTANT functionality:
    - Developer prompt actually generates working code
    - Evaluator prompt actually reviews code quality
    - QA prompt actually runs tests and validates

    If these tests fail, the entire Docker isolation strategy is broken.
    """

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_developer_prompt_generates_simple_function(self, real_git_repo, real_repo_url, oauth_token):
        """
        Test that developer container with coder.md prompt actually writes code.

        This is a CRITICAL test that validates:
        - Container can execute and clone REAL repository
        - Claude API is accessible
        - Prompt produces valid Python code
        - Code is committed to git
        - Changes can be pushed to real GitHub repo
        """
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        # Create spec for simple function
        spec_name = "add-function-e2e"
        spec_dir = real_git_repo / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True, exist_ok=True)

        spec_content = """# Add Function

## Objective
Create a simple Python function that adds two numbers.

## Requirements
- Create file `calculator.py` in project root
- Function named `add` that takes parameters `a` and `b`
- Return the sum of a and b

## Acceptance Criteria
- File calculator.py exists
- Function add(2, 3) returns 5
"""
        (spec_dir / "spec.md").write_text(spec_content)

        plan = {
            "feature": "Add simple calculator function",
            "phases": [
                {
                    "name": "coding",
                    "description": "Implement calculator.py with add function"
                }
            ],
            "subtasks": [{
                "id": "task-1",
                "description": "Create calculator.py with add function",
                "status": "pending"
            }]
        }
        (spec_dir / "implementation_plan.json").write_text(json.dumps(plan))

        # Set up strategy with REAL repository URL
        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url  # Use REAL GitHub repository
        )

        strategy.setup()

        # Run REAL WORKFLOW - This will actually:
        # 1. Start Docker container
        # 2. Clone the real GitHub repository
        # 3. Run Claude SDK to generate code
        # 4. Commit and push changes
        result = await strategy.run_pipeline(
            spec_name=spec_name,
            plan=plan
        )

        # Validate pipeline succeeded
        assert result is True, "Pipeline failed to complete successfully"

        # Verify task logs show completion
        log_file = spec_dir / "task_logs.json"
        assert log_file.exists(), "Task logs were not created"

        logs = json.loads(log_file.read_text())
        assert logs["workflow_status"] in ["ready_for_review", "completed"], \
            f"Unexpected workflow status: {logs['workflow_status']}"

        # Check out the branch and verify file was created
        subprocess.run(
            ["git", "checkout", f"auto-claude/{spec_name}"],
            cwd=real_git_repo,
            capture_output=True
        )

        calc_file = real_git_repo / "calculator.py"
        assert calc_file.exists(), "calculator.py was not created"

        # Verify the function actually works
        calc_code = calc_file.read_text()
        assert "def add" in calc_code, "add function not found in calculator.py"

        # Actually test the function
        namespace = {}
        exec(calc_code, namespace)
        assert "add" in namespace, "add function not in namespace"
        assert namespace["add"](2, 3) == 5, "add(2, 3) should return 5"

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_evaluator_prompt_reviews_code_quality(self, real_git_repo, real_repo_url, oauth_token):
        """
        Test that evaluator container actually reviews code.

        Validates:
        - Evaluator can execute
        - Evaluator identifies code quality issues
        - Feedback is meaningful and actionable
        """
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        # Create intentionally bad code
        bad_code = """# Bad code with multiple issues
def calc(x,y):  # Poor naming, no spaces
    z=x+y  # No spaces around operators
    return z  # Unnecessary variable

def process_data(data):
    # No error handling
    return data['value']  # Will crash if 'value' not in dict
"""

        bad_file = real_git_repo / "bad_code.py"
        bad_file.write_text(bad_code)

        # Commit the bad code
        subprocess.run(["git", "add", "."], cwd=real_git_repo, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", "Add bad code"],
            cwd=real_git_repo,
            capture_output=True,
            text=True
        )

        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=real_git_repo,
            capture_output=True,
            text=True
        ).stdout.strip()

        # Run evaluator
        spec_name = "code-review-e2e"
        spec_dir = real_git_repo / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True, exist_ok=True)

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        strategy.setup()

        result = await strategy._orchestrator.run_evaluator(
            spec_name=spec_name,
            branch_name="main",
            commit_sha=commit_sha
        )

        # Evaluator should identify issues
        assert result.success, f"Evaluator failed to run:\n{result.output}"

        # Check for meaningful feedback
        # Evaluator should find at least some of these issues:
        # - Poor naming
        # - Missing error handling
        # - Style issues
        output_lower = result.output.lower()
        has_feedback = (
            "naming" in output_lower or
            "error" in output_lower or
            "style" in output_lower or
            "quality" in output_lower or
            len(result.comments) > 0
        )

        assert has_feedback, \
            f"Evaluator should provide feedback on code issues.\nOutput: {result.output}"

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_qa_prompt_runs_tests_and_detects_failures(self, real_git_repo, real_repo_url, oauth_token):
        """
        Test that QA container actually runs tests.

        Validates:
        - QA can execute tests
        - Test failures are detected
        - Test results are reported correctly
        """
        from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

        # Create code with intentional bug
        code_file = real_git_repo / "calculator.py"
        code_file.write_text("""def subtract(a, b):
    return b - a  # BUG: Should be a - b
""")

        # Create test that will fail due to bug
        test_dir = real_git_repo / "tests"
        test_dir.mkdir(exist_ok=True)
        test_file = test_dir / "test_calculator.py"
        test_file.write_text("""from calculator import subtract

def test_subtract():
    # This will fail due to our intentional bug
    assert subtract(10, 5) == 5, "10 - 5 should equal 5"
""")

        # Commit code and tests
        subprocess.run(["git", "add", "."], cwd=real_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add code with bug"],
            cwd=real_git_repo,
            capture_output=True
        )

        commit_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=real_git_repo,
            capture_output=True,
            text=True
        ).stdout.strip()

        # Run QA
        spec_name = "qa-test-e2e"
        spec_dir = real_git_repo / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True, exist_ok=True)

        strategy = DockerIsolationStrategy(
            project_dir=real_git_repo,
            base_branch="main",
            repo_url=real_repo_url
        )

        strategy.setup()

        result = await strategy._orchestrator.run_qa(
            spec_name=spec_name,
            branch_name="main",
            commit_sha=commit_sha
        )

        # QA should detect the failing test
        assert not result.success, \
            "QA should have detected the failing test"

        output_lower = result.output.lower()
        assert "test_subtract" in output_lower or "subtract" in output_lower, \
            f"QA output should mention the failing test.\nOutput: {result.output}"


class TestFullPipeline:
    """
    Test complete Developer → Evaluator → QA pipeline.

    This validates the entire workflow works end-to-end.
    """

    @pytest.mark.slow
    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_complete_pipeline_simple_feature(self, real_git_repo, real_repo_url, oauth_token):
        """
        Test complete pipeline for a simple feature.

        This is the ULTIMATE integration test:
        1. Developer generates code from spec
        2. Evaluator reviews code quality
        3. QA runs tests
        4. All steps pass

        If this test passes, the Docker isolation strategy is working correctly.
        """
        pytest.skip("TODO: Implement full pipeline test - requires significant time and API credits")
        # This test would:
        # - Create a simple spec
        # - Run full pipeline
        # - Verify all containers execute correctly
        # - Verify code is generated, reviewed, and tested
        # - This is expensive so we skip for now


# Mark all tests in this file as e2e
pytest.mark.e2e = pytest.mark.e2e
