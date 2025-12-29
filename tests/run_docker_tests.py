#!/usr/bin/env python3
"""
Convenient test runner for Docker isolation tests.

Usage:
    python tests/run_docker_tests.py              # Run all tests
    python tests/run_docker_tests.py --fast       # Run only unit tests
    python tests/run_docker_tests.py --coverage   # Run with coverage report
    python tests/run_docker_tests.py --watch      # Watch mode (requires pytest-watch)
"""

import sys
import subprocess
from pathlib import Path


def run_tests(args):
    """Run pytest with specified arguments."""
    base_cmd = [
        sys.executable, "-m", "pytest",
        "tests/test_docker_strategy.py",
        "tests/test_docker_orchestrator.py",
        "tests/test_container_lifecycle.py",
        "tests/test_workflow_state_machine.py",
        "tests/test_docker_integration.py",
        "-v",
        "--tb=short",  # Short traceback format
    ]

    if "--fast" in args:
        print("Running unit tests only (fast mode)...")
        base_cmd.extend(["-m", "not slow"])

    if "--coverage" in args:
        print("Running with coverage...")
        base_cmd.extend([
            "--cov=apps.backend.core.isolation",
            "--cov-report=html",
            "--cov-report=term-missing"
        ])

    if "--watch" in args:
        print("Running in watch mode...")
        # Use pytest-watch if available
        try:
            subprocess.run(["ptw", "--"] + base_cmd[3:], check=True)
            return 0
        except FileNotFoundError:
            print("ERROR: pytest-watch not installed. Install with: pip install pytest-watch")
            return 1

    # Add any additional pytest args
    extra_args = [arg for arg in args if not arg.startswith("--") or arg not in ["--fast", "--coverage", "--watch"]]
    base_cmd.extend(extra_args)

    print(f"Running: {' '.join(base_cmd)}")
    result = subprocess.run(base_cmd)
    return result.returncode


def main():
    """Main entry point."""
    # Change to project root
    project_root = Path(__file__).parent.parent
    print(f"Project root: {project_root}")

    args = sys.argv[1:]

    # Show help
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0

    # Run tests
    return run_tests(args)


if __name__ == "__main__":
    sys.exit(main())
