#!/usr/bin/env python3
"""
Evaluator Agent - Container Script
===================================

Runs inside Docker container to review code quality against best practices.

Environment Variables:
    REPO_URL: Git repository URL to clone
    BRANCH_NAME: Branch to evaluate
    CLAUDE_CODE_OAUTH_TOKEN: OAuth token for Claude SDK
    MODEL: Claude model to use (default: claude-3-7-sonnet-20250219)
    MAX_TURNS: Maximum conversation turns (default: 50)

Output:
    FEEDBACK_JSON={"approved": true/false, "comments": [...]} on stdout
    Exit code 0 always (approval status in JSON)
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


def get_changed_files(repo_dir: Path, base_branch: str = "main") -> list[str]:
    """
    Get list of files changed compared to base branch.

    Args:
        repo_dir: Repository directory
        base_branch: Base branch to compare against

    Returns:
        List of changed file paths
    """
    logger.info(f"Getting changed files compared to {base_branch}")

    # Fetch base branch
    run_command(["git", "fetch", "origin", base_branch], cwd=repo_dir)

    # Get diff
    result = run_command(
        ["git", "diff", f"origin/{base_branch}", "--name-only"],
        cwd=repo_dir,
    )

    files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    logger.info(f"Found {len(files)} changed files")
    return files


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt file from the prompts directory.

    Args:
        prompt_name: Name of the prompt file (e.g., 'qa_reviewer.md')

    Returns:
        Prompt content as string
    """
    # Assume prompts are mounted in the container at /app/prompts
    prompt_path = Path("/app/prompts") / prompt_name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    logger.debug(f"Loading prompt: {prompt_path}")
    return prompt_path.read_text()


def run_code_review(
    repo_dir: Path,
    changed_files: list[str],
    model: str = "claude-3-7-sonnet-20250219",
    max_turns: int = 50,
) -> dict:
    """
    Run Claude SDK to review code quality.

    Args:
        repo_dir: Repository directory
        changed_files: List of changed files to review
        model: Claude model to use
        max_turns: Maximum conversation turns

    Returns:
        Feedback dictionary with approval status and comments
    """
    logger.info("Starting code review with Claude SDK")

    # Import Claude SDK
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except ImportError as e:
        logger.error(f"Failed to import Claude SDK: {e}")
        logger.error("Make sure claude-agent-sdk is installed")
        raise

    # Load QA reviewer prompt
    qa_prompt = load_prompt("qa_reviewer.md")

    # Build context
    env_context = f"""
YOUR ENVIRONMENT
================

Working Directory: {repo_dir.resolve()}

CHANGED FILES TO REVIEW:
{json.dumps(changed_files, indent=2)}

Your task is to review these changes for:
1. Code quality and best practices
2. Security vulnerabilities
3. Performance issues
4. Error handling
5. Test coverage
6. Documentation completeness

Provide feedback in the following JSON format:
{{
    "approved": true/false,
    "comments": [
        {{
            "message": "Description of issue or observation",
            "file_path": "path/to/file.py",
            "line_number": 42,
            "severity": "error|warning|info"
        }}
    ]
}}
"""

    # Create full prompt
    full_prompt = f"{env_context}\n\n{qa_prompt}"

    # Create client
    logger.info(f"Creating Claude SDK client with model: {model}")

    # Basic security settings for container
    settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",
            "allow": [
                "Read(./**)",
                "Glob(./**)",
                "Grep(./**)",
                "Bash(*)",
            ],
        },
    }

    settings_file = repo_dir / ".claude_settings.json"
    with open(settings_file, "w") as f:
        json.dump(settings, f, indent=2)

    client = ClaudeSDKClient(
        options=ClaudeAgentOptions(
            model=model,
            system_prompt=full_prompt,
            allowed_tools=["Read", "Glob", "Grep", "Bash"],
            max_turns=max_turns,
            cwd=str(repo_dir.resolve()),
            settings=str(settings_file.resolve()),
            max_thinking_tokens=10000,  # Enable extended thinking for thorough review
        )
    )

    # Run the agent
    logger.info("Starting review session...")
    try:
        # Send initial message to trigger review
        response = client.send_message(
            "Please review the changed files and provide feedback in the specified JSON format. "
            "Be thorough and check for security issues, code quality, and best practices."
        )

        logger.info(f"Review session completed with {len(response)} responses")

        # Extract JSON from the last response
        # Claude should provide JSON in the response
        last_response = response[-1] if response else None
        if not last_response:
            raise ValueError("No response from Claude")

        # Try to parse JSON from response
        # Look for JSON in the response text
        response_text = str(last_response)
        try:
            # Try to find JSON in response
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                feedback = json.loads(json_text)
            else:
                # No JSON found, create default response
                logger.warning("No JSON found in response, creating default feedback")
                feedback = {
                    "approved": True,
                    "comments": [],
                }
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from response: {e}")
            feedback = {
                "approved": True,
                "comments": [],
            }

        logger.info(f"Review complete. Approved: {feedback.get('approved', False)}")
        return feedback

    except Exception as e:
        logger.error(f"Review session failed: {e}", exc_info=True)
        # Return non-approved feedback on error
        return {
            "approved": False,
            "comments": [
                {
                    "message": f"Code review failed: {str(e)}",
                    "file_path": "",
                    "line_number": 0,
                    "severity": "error",
                }
            ],
        }


def main() -> int:
    """
    Main entry point for evaluator agent.

    Returns:
        Exit code (0 always, approval status in JSON output)
    """
    logger.info("Evaluator Agent starting...")

    # Validate environment variables
    required_vars = ["REPO_URL", "BRANCH_NAME"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        # Output error as JSON
        error_feedback = {
            "approved": False,
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

    # Check for OAuth token
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        logger.error("CLAUDE_CODE_OAUTH_TOKEN environment variable not set")
        error_feedback = {
            "approved": False,
            "comments": [
                {
                    "message": "CLAUDE_CODE_OAUTH_TOKEN not set",
                    "file_path": "",
                    "line_number": 0,
                    "severity": "error",
                }
            ],
        }
        print(f"FEEDBACK_JSON={json.dumps(error_feedback)}", file=sys.stdout)
        return 0

    # Parse environment variables
    repo_url = os.environ["REPO_URL"]
    branch_name = os.environ["BRANCH_NAME"]
    model = os.environ.get("MODEL", "claude-3-7-sonnet-20250219")
    max_turns = int(os.environ.get("MAX_TURNS", "50"))
    base_branch = os.environ.get("BASE_BRANCH", "main")

    # Create temporary working directory
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"

        try:
            # Clone repository and checkout branch
            clone_repository(repo_url, repo_dir, branch_name)

            # Get changed files
            changed_files = get_changed_files(repo_dir, base_branch)

            # Run code review
            feedback = run_code_review(
                repo_dir,
                changed_files,
                model,
                max_turns,
            )

            # Output feedback (used by orchestrator)
            print(f"FEEDBACK_JSON={json.dumps(feedback)}", file=sys.stdout)

            logger.info("Evaluator Agent completed successfully")
            return 0

        except Exception as e:
            logger.error(f"Evaluator Agent failed: {e}", exc_info=True)
            # Output error as feedback
            error_feedback = {
                "approved": False,
                "comments": [
                    {
                        "message": f"Evaluation failed: {str(e)}",
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
