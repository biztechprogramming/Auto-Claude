#!/usr/bin/env python3
"""
Developer Agent - Container Script
===================================

Runs inside Docker container to implement code based on an implementation plan.

Environment Variables:
    REPO_URL: Git repository URL to clone
    BASE_BRANCH: Base branch to create feature branch from (e.g., main, develop)
    BRANCH_NAME: Feature branch name to create/checkout
    IMPLEMENTATION_PLAN: JSON string containing the implementation plan
    FEEDBACK_COMMENTS: JSON string containing feedback from previous iteration (optional)
    CLAUDE_CODE_OAUTH_TOKEN: OAuth token for Claude SDK
    MODEL: Claude model to use (default: claude-3-7-sonnet-20250219)
    MAX_TURNS: Maximum conversation turns (default: 100)

Output:
    COMMIT_SHA=<sha> on stdout
    Exit code 0 on success, non-zero on failure
"""

import asyncio
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


def clone_repository(repo_url: str, target_dir: Path) -> None:
    """
    Clone git repository with depth=1 for faster cloning.

    Args:
        repo_url: Repository URL
        target_dir: Target directory for clone
    """
    logger.info(f"Cloning repository: {repo_url}")
    run_command(
        ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
    )
    logger.info("Repository cloned successfully")


def setup_branch(repo_dir: Path, base_branch: str, branch_name: str) -> None:
    """
    Create or checkout feature branch from base branch.

    Args:
        repo_dir: Repository directory
        base_branch: Base branch to create from
        branch_name: Feature branch name
    """
    logger.info(f"Setting up branch: {branch_name} from {base_branch}")

    # Fetch base branch
    logger.info(f"Fetching base branch: {base_branch}")
    run_command(["git", "fetch", "origin", base_branch], cwd=repo_dir)

    # Check if branch exists remotely
    result = run_command(
        ["git", "ls-remote", "--heads", "origin", branch_name],
        cwd=repo_dir,
        check=False,
    )

    if result.stdout.strip():
        # Branch exists, check it out
        logger.info(f"Branch {branch_name} exists, checking out")
        run_command(["git", "checkout", branch_name], cwd=repo_dir)
        run_command(["git", "pull", "origin", branch_name], cwd=repo_dir)
    else:
        # Create new branch from base
        logger.info(f"Creating new branch {branch_name} from {base_branch}")
        run_command(["git", "checkout", "-b", branch_name, f"origin/{base_branch}"], cwd=repo_dir)

    logger.info("Branch setup complete")


def load_prompt(prompt_name: str) -> str:
    """
    Load a prompt file from the prompts directory.

    Args:
        prompt_name: Name of the prompt file (e.g., 'coder.md')

    Returns:
        Prompt content as string
    """
    # Assume prompts are mounted in the container at /app/prompts
    prompt_path = Path("/app/prompts") / prompt_name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    logger.debug(f"Loading prompt: {prompt_path}")
    return prompt_path.read_text()


async def run_implementation(
    repo_dir: Path,
    implementation_plan: dict,
    feedback_comments: list[dict] | None = None,
    model: str = "claude-3-7-sonnet-20250219",
    max_turns: int = 100,
) -> str:
    """
    Run Claude SDK to implement the plan.

    Args:
        repo_dir: Repository directory
        implementation_plan: Implementation plan dictionary
        feedback_comments: Optional feedback from previous iteration
        model: Claude model to use
        max_turns: Maximum conversation turns

    Returns:
        Final commit SHA
    """
    logger.info("Starting implementation with Claude SDK")

    # Import Claude SDK
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
    except ImportError as e:
        logger.error(f"Failed to import Claude SDK: {e}")
        logger.error("Make sure claude-agent-sdk is installed")
        raise

    # Load coder prompt
    coder_prompt = load_prompt("coder.md")

    # Build environment context
    env_context = f"""
YOUR ENVIRONMENT
================

Working Directory: {repo_dir.resolve()}
Spec Location: ./.auto-claude/specs/container-build/

IMPLEMENTATION PLAN:
{json.dumps(implementation_plan, indent=2)}
"""

    if feedback_comments:
        env_context += f"""

FEEDBACK FROM PREVIOUS ITERATION:
{json.dumps(feedback_comments, indent=2)}

Please address all feedback comments before proceeding.
"""

    # Create full prompt
    full_prompt = f"{env_context}\n\n{coder_prompt}"

    # Create client
    logger.info(f"Creating Claude SDK client with model: {model}")

    # Basic security settings for container
    settings = {
        "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
        "permissions": {
            "defaultMode": "acceptEdits",
            "allow": [
                "Read(./**)",
                "Write(./**)",
                "Edit(./**)",
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
            allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Bash"],
            max_turns=max_turns,
            cwd=str(repo_dir.resolve()),
            settings=str(settings_file.resolve()),
        )
    )

    # Run the agent
    logger.info("Starting agent session...")
    print(">>> AGENT SESSION STARTING <<<", flush=True)

    try:
        # Send initial message to trigger implementation
        message = (
            "Please implement the next pending subtask according to the implementation plan. "
            "Follow all steps in the coder prompt."
        )

        logger.info("Connecting to Claude SDK...")
        print(">>> Connecting to Claude SDK...", flush=True)

        async with client:
            logger.info("Connected! Sending query to Claude SDK...")
            print(">>> Connected! Sending query...", flush=True)
            await client.query(message)

            # Collect response
            message_count = 0
            print(">>> Receiving responses...", flush=True)
            async for msg in client.receive_response():
                message_count += 1
                msg_type = type(msg).__name__
                logger.debug(f"Received message #{message_count}: {msg_type}")

                # Handle AssistantMessage (text and tool use)
                if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                    for block in msg.content:
                        block_type = type(block).__name__

                        if block_type == "TextBlock" and hasattr(block, "text"):
                            # Log agent text output
                            text_preview = block.text[:200] if len(block.text) > 200 else block.text
                            logger.info(f"Agent: {text_preview}")
                            print(f">>> Agent response: {text_preview}", flush=True)
                        elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                            # Log tool usage
                            logger.info(f"Tool used: {block.name}")
                            print(f">>> Tool: {block.name}", flush=True)

            logger.info(f"Agent session completed with {message_count} messages")
            print(f">>> Session complete! {message_count} messages received", flush=True)

        # Get the latest commit SHA
        print(">>> Getting commit SHA...", flush=True)
        result = run_command(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
        )
        commit_sha = result.stdout.strip()
        logger.info(f"Implementation complete. Commit SHA: {commit_sha}")
        print(f">>> COMMIT SHA: {commit_sha}", flush=True)

        return commit_sha

    except Exception as e:
        logger.error(f"Agent session failed: {e}", exc_info=True)
        print(f">>> ERROR: {e}", flush=True)
        raise


def push_changes(repo_dir: Path, branch_name: str) -> None:
    """
    Push changes to remote repository.

    Args:
        repo_dir: Repository directory
        branch_name: Branch to push
    """
    logger.info(f"Pushing changes to origin/{branch_name}")
    run_command(
        ["git", "push", "origin", branch_name],
        cwd=repo_dir,
    )
    logger.info("Changes pushed successfully")


def main() -> int:
    """
    Main entry point for developer agent.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    logger.info("Developer Agent starting...")

    # Validate environment variables
    required_vars = ["REPO_URL", "BASE_BRANCH", "BRANCH_NAME", "IMPLEMENTATION_PLAN"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]

    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        return 1

    # Check for OAuth token
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        logger.error("CLAUDE_CODE_OAUTH_TOKEN environment variable not set")
        logger.error("Run 'claude setup-token' to configure authentication")
        return 1

    # Parse environment variables
    repo_url = os.environ["REPO_URL"]
    base_branch = os.environ["BASE_BRANCH"]
    branch_name = os.environ["BRANCH_NAME"]
    model = os.environ.get("MODEL", "claude-3-7-sonnet-20250219")
    max_turns = int(os.environ.get("MAX_TURNS", "100"))

    try:
        implementation_plan = json.loads(os.environ["IMPLEMENTATION_PLAN"])
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse IMPLEMENTATION_PLAN: {e}")
        return 1

    feedback_comments = None
    if os.environ.get("FEEDBACK_COMMENTS"):
        try:
            feedback_comments = json.loads(os.environ["FEEDBACK_COMMENTS"])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse FEEDBACK_COMMENTS: {e}")
            return 1

    # Create temporary working directory
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "repo"

        try:
            # Configure gh CLI to use git authentication
            # gh reads GH_TOKEN from environment and sets up git credential helper
            print(">>> Configuring GitHub authentication...", flush=True)
            run_command(["gh", "auth", "setup-git"])

            # Clone repository
            clone_repository(repo_url, repo_dir)

            # Setup branch
            setup_branch(repo_dir, base_branch, branch_name)

            # Run implementation (async)
            commit_sha = asyncio.run(
                run_implementation(
                    repo_dir,
                    implementation_plan,
                    feedback_comments,
                    model,
                    max_turns,
                )
            )

            # Push changes
            push_changes(repo_dir, branch_name)

            # Output commit SHA (used by orchestrator)
            print(f"COMMIT_SHA={commit_sha}", file=sys.stdout)

            logger.info("Developer Agent completed successfully")
            return 0

        except Exception as e:
            logger.error(f"Developer Agent failed: {e}", exc_info=True)
            return 1


if __name__ == "__main__":
    sys.exit(main())
