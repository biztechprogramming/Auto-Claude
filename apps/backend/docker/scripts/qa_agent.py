#!/usr/bin/env python3
"""
QA Agent - Container Script
============================

Runs inside Docker container to execute tests and validate functionality.

Environment Variables:
    REPO_URL: Git repository URL to clone
    BRANCH_NAME: Branch to test
    CLAUDE_CODE_OAUTH_TOKEN: OAuth token for Claude SDK (optional for basic tests)
    MODEL: Claude model to use for intelligent test analysis (default: claude-3-7-sonnet-20250219)
    TEST_COMMAND: Custom test command to run (optional, auto-detected if not set)
    PLAYWRIGHT_ENABLED: Set to 'true' to run Playwright tests (default: false)

Output:
    FEEDBACK_JSON={"passed": true/false, "comments": [...]} on stdout
    Exit code 0 always (pass/fail status in JSON)
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)


def run_command(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command and return the result.

    Args:
        cmd: Command and arguments as list
        cwd: Working directory (optional)
        check: Raise exception on non-zero exit code

    Returns:
        CompletedProcess instance

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
    """
    logger.debug(f"Running command: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check,
        )
        if result.stdout:
            logger.debug(f"stdout: {result.stdout[:500]}")
        if result.stderr:
            logger.debug(f"stderr: {result.stderr[:500]}")
        return result
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.error(f"Exit code: {e.returncode}")
        logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        raise


def clone_repository(repo_url: str, target_dir: Path, branch_name: str) -> None:
    """
    Clone git repository and checkout specific branch.

    Args:
        repo_url: Repository URL
        target_dir: Target directory for clone
        branch_name: Branch to checkout
    """
    logger.info(f"Cloning repository: {repo_url}")
    run_command(
        ["git", "clone", repo_url, str(target_dir)],
    )

    logger.info(f"Checking out branch: {branch_name}")
    run_command(
        ["git", "checkout", branch_name],
        cwd=target_dir,
    )
    logger.info("Repository cloned and branch checked out successfully")


def detect_test_framework(repo_dir: Path) -> str | None:
    """
    Detect the test framework used in the project.

    Args:
        repo_dir: Repository directory

    Returns:
        Test command to run, or None if not detected
    """
    logger.info("Detecting test framework...")

    # Check for package.json (Node.js projects)
    package_json = repo_dir / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})

                # Check for test script
                if "test" in scripts:
                    logger.info("Detected npm test command")
                    return "npm test"
                elif "test:unit" in scripts:
                    logger.info("Detected npm run test:unit command")
                    return "npm run test:unit"
        except json.JSONDecodeError:
            logger.warning("Failed to parse package.json")

    # Check for pytest (Python projects)
    if (repo_dir / "pytest.ini").exists() or (repo_dir / "setup.py").exists():
        logger.info("Detected pytest")
        return "pytest"

    # Check for requirements.txt with pytest
    requirements = repo_dir / "requirements.txt"
    if requirements.exists():
        content = requirements.read_text()
        if "pytest" in content:
            logger.info("Detected pytest in requirements.txt")
            return "pytest"

    # Check for go.mod (Go projects)
    if (repo_dir / "go.mod").exists():
        logger.info("Detected Go project")
        return "go test ./..."

    # Check for Cargo.toml (Rust projects)
    if (repo_dir / "Cargo.toml").exists():
        logger.info("Detected Rust project")
        return "cargo test"

    logger.warning("Could not detect test framework")
    return None


def run_tests(repo_dir: Path, test_command: str | None = None) -> tuple[bool, str, str]:
    """
    Run tests for the project.

    Args:
        repo_dir: Repository directory
        test_command: Test command to run (auto-detected if None)

    Returns:
        Tuple of (success, stdout, stderr)
    """
    # Detect test command if not provided
    if not test_command:
        test_command = detect_test_framework(repo_dir)
        if not test_command:
            logger.warning("No test framework detected, skipping tests")
            return True, "No tests found", ""

    logger.info(f"Running tests: {test_command}")

    # Run test command
    result = run_command(
        test_command.split(),
        cwd=repo_dir,
        check=False,
    )

    success = result.returncode == 0
    logger.info(f"Tests {'passed' if success else 'failed'} (exit code: {result.returncode})")

    return success, result.stdout, result.stderr


def run_playwright_tests(repo_dir: Path) -> tuple[bool, str, str]:
    """
    Run Playwright tests if configured.

    Args:
        repo_dir: Repository directory

    Returns:
        Tuple of (success, stdout, stderr)
    """
    logger.info("Running Playwright tests...")

    # Check if Playwright is configured
    package_json = repo_dir / "package.json"
    if not package_json.exists():
        logger.warning("No package.json found, skipping Playwright tests")
        return True, "No Playwright tests found", ""

    try:
        with open(package_json) as f:
            pkg = json.load(f)
            scripts = pkg.get("scripts", {})

            # Check for Playwright test script
            playwright_script = None
            for script_name in ["test:e2e", "test:playwright", "playwright"]:
                if script_name in scripts:
                    playwright_script = script_name
                    break

            if not playwright_script:
                logger.warning("No Playwright test script found")
                return True, "No Playwright tests configured", ""

            logger.info(f"Running: npm run {playwright_script}")
            result = run_command(
                ["npm", "run", playwright_script],
                cwd=repo_dir,
                check=False,
            )

            success = result.returncode == 0
            logger.info(f"Playwright tests {'passed' if success else 'failed'}")

            return success, result.stdout, result.stderr

    except json.JSONDecodeError:
        logger.error("Failed to parse package.json")
        return False, "", "Failed to parse package.json"


def parse_test_failures(stdout: str, stderr: str) -> list[dict]:
    """
    Parse test output to extract failure information.

    Args:
        stdout: Test stdout
        stderr: Test stderr

    Returns:
        List of failure comments
    """
    comments = []
    output = stdout + "\n" + stderr

    # Look for common test failure patterns
    lines = output.split("\n")
    for i, line in enumerate(lines):
        # Jest/Mocha patterns
        if "FAIL" in line or "✕" in line or "Error:" in line:
            # Extract file and test name if possible
            file_path = ""
            message = line.strip()

            # Try to find file path in surrounding lines
            for j in range(max(0, i - 5), min(len(lines), i + 5)):
                if ".test." in lines[j] or ".spec." in lines[j]:
                    parts = lines[j].strip().split()
                    for part in parts:
                        if ".test." in part or ".spec." in part:
                            file_path = part
                            break

            comments.append(
                {
                    "message": f"Test failed: {message}",
                    "file_path": file_path,
                    "line_number": 0,
                    "severity": "error",
                }
            )

        # Pytest patterns
        elif "FAILED" in line:
            parts = line.split("::")
            if len(parts) >= 2:
                file_path = parts[0].strip()
                test_name = parts[1].strip() if len(parts) > 1 else ""
                message = f"Test failed: {test_name}"

                comments.append(
                    {
                        "message": message,
                        "file_path": file_path,
                        "line_number": 0,
                        "severity": "error",
                    }
                )

    # If no specific failures found but tests failed, add generic message
    if not comments and (stdout or stderr):
        comments.append(
            {
                "message": "Tests failed. See output for details.",
                "file_path": "",
                "line_number": 0,
                "severity": "error",
            }
        )

    return comments


def main() -> int:
    """
    Main entry point for QA agent.

    Returns:
        Exit code (0 always, pass/fail status in JSON output)
    """
    logger.info("QA Agent starting...")

    # Validate environment variables
    required_vars = ["REPO_URL", "BRANCH_NAME"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        # Output error as JSON
        error_feedback = {
            "passed": False,
            "comments": [
                {
                    "message": f"Missing environment variables: {', '.join(missing_vars)}",
                    "file_path": "",
                    "line_number": 0,
                    "severity": "error",
                }
            ],
        }
        print(f"FEEDBACK_JSON={json.dumps(error_feedback)}", file=sys.stdout)
        return 0  # Always exit 0, status is in JSON

    # Parse environment variables
    repo_url = os.environ["REPO_URL"]
    branch_name = os.environ["BRANCH_NAME"]
    test_command = os.environ.get("TEST_COMMAND")
    playwright_enabled = os.environ.get("PLAYWRIGHT_ENABLED", "false").lower() == "true"

    # Create temporary working directory
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"

        try:
            # Clone repository and checkout branch
            clone_repository(repo_url, repo_dir, branch_name)

            # Install dependencies
            logger.info("Installing dependencies...")
            if (repo_dir / "package.json").exists():
                run_command(["npm", "install"], cwd=repo_dir, check=False)
            elif (repo_dir / "requirements.txt").exists():
                run_command(
                    ["pip", "install", "-r", "requirements.txt"],
                    cwd=repo_dir,
                    check=False,
                )

            # Run unit/integration tests
            test_passed, test_stdout, test_stderr = run_tests(repo_dir, test_command)
            comments = []

            if not test_passed:
                logger.warning("Unit tests failed")
                comments.extend(parse_test_failures(test_stdout, test_stderr))

            # Run Playwright tests if enabled
            if playwright_enabled:
                pw_passed, pw_stdout, pw_stderr = run_playwright_tests(repo_dir)
                if not pw_passed:
                    logger.warning("Playwright tests failed")
                    playwright_comments = parse_test_failures(pw_stdout, pw_stderr)
                    # Mark as Playwright failures
                    for comment in playwright_comments:
                        comment["message"] = f"[Playwright] {comment['message']}"
                    comments.extend(playwright_comments)
                test_passed = test_passed and pw_passed

            # Build feedback
            feedback = {
                "passed": test_passed,
                "comments": comments if comments else [],
            }

            # Output feedback (used by orchestrator)
            print(f"FEEDBACK_JSON={json.dumps(feedback)}", file=sys.stdout)

            logger.info(f"QA Agent completed. Tests {'passed' if test_passed else 'failed'}")
            return 0

        except Exception as e:
            logger.error(f"QA Agent failed: {e}", exc_info=True)
            # Output error as feedback
            error_feedback = {
                "passed": False,
                "comments": [
                    {
                        "message": f"QA test execution failed: {str(e)}",
                        "file_path": "",
                        "line_number": 0,
                        "severity": "error",
                    }
                ],
            }
            print(f"FEEDBACK_JSON={json.dumps(error_feedback)}", file=sys.stdout)
            return 0  # Always exit 0


if __name__ == "__main__":
    sys.exit(main())
