"""
Test script for FastAPI-based Docker container communication.

This demonstrates:
1. Starting a container with FastAPI server
2. Waiting for it to be ready
3. Sending a task via POST /start
4. Streaming logs in real-time
5. Monitoring status
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from core.isolation.container_client import ContainerClient, ContainerConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def print_log(log_entry: dict):
    """Print a log entry."""
    timestamp = log_entry.get("timestamp", "")
    level = log_entry.get("level", "INFO")
    message = log_entry.get("message", "")
    print(f"[{level}] {message}")


async def main():
    """Test the FastAPI container."""

    # Get environment variables
    gh_token = os.environ.get("GH_TOKEN")
    if not gh_token:
        logger.error("GH_TOKEN not set in environment")
        return 1

    claude_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not claude_token:
        logger.error("CLAUDE_CODE_OAUTH_TOKEN not set")
        return 1

    # Configure container
    config = ContainerConfig(
        name="test-fastapi-dev",
        image="auto-claude-dev:latest",
        port=8001,
        env_vars={
            "GH_TOKEN": gh_token,
            "CLAUDE_CODE_OAUTH_TOKEN": claude_token,
        }
    )

    client = ContainerClient(config)

    try:
        # Start container
        logger.info("=" * 70)
        logger.info("STARTING FASTAPI CONTAINER TEST")
        logger.info("=" * 70)

        client.start_container()

        # Wait for API to be ready
        if not client.wait_for_ready(timeout=30):
            logger.error("Container API did not become ready")
            return 1

        # Start streaming logs in background
        logger.info("Starting log stream...")
        log_task = asyncio.create_task(client.stream_logs(print_log))

        # Start the development task
        task_data = {
            "repo_url": "https://github.com/biztechprogramming/Auto-Claude.git",
            "base_branch": "develop",
            "branch_name": "auto-claude/test-fastapi-001",
            "spec_name": "test-fastapi-001",
            "task_description": "Test FastAPI container communication with GitHub push"
        }

        logger.info("\n" + "=" * 70)
        logger.info("STARTING DEVELOPMENT TASK")
        logger.info("=" * 70 + "\n")

        await client.start_task(task_data)

        # Wait for completion
        logger.info("Waiting for task to complete...")
        final_status = await client.wait_for_completion(timeout=300)  # 5 minute timeout

        logger.info("\n" + "=" * 70)
        logger.info("TASK COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        logger.info(f"Status: {final_status}")

        # Cancel log streaming
        log_task.cancel()

        # Get final logs
        logs = await client.get_logs(count=50)
        logger.info("\nFinal 50 log entries:")
        for log in logs:
            print_log(log)

        return 0

    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return 1

    finally:
        # Cleanup
        logger.info("\nCleaning up...")
        client.stop_container()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
