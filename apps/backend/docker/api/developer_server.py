"""
Developer Container FastAPI Server.

Runs on port 8001 and handles development tasks.
"""

import os
import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from base_server import BaseContainerServer, StartRequest, TaskStatus, create_start_endpoint

logger = logging.getLogger(__name__)


class DeveloperServer(BaseContainerServer):
    """Developer container server."""

    def __init__(self):
        super().__init__(name="Developer", port=8001)
        create_start_endpoint(self)

    async def _run_task(self, request: StartRequest):
        """Execute development task."""
        try:
            logger.info("=" * 70)
            logger.info("DEVELOPER AGENT STARTING")
            logger.info("=" * 70)

            # Get GitHub token
            gh_token = os.environ.get("GH_TOKEN")
            if not gh_token:
                raise ValueError("GH_TOKEN environment variable not set")

            logger.info("GitHub token found")

            # Create temporary workspace
            with tempfile.TemporaryDirectory() as temp_dir:
                repo_dir = Path(temp_dir) / "repo"

                # Authenticate GitHub
                await self._authenticate_github(gh_token)

                # Clone repository
                await self._clone_repository(request.repo_url, repo_dir)

                # Setup branch
                await self._setup_branch(repo_dir, request.base_branch, request.branch_name)

                # Run implementation (TODO: integrate with Claude SDK)
                logger.info("Starting implementation...")
                logger.info(f"Task: {request.task_description}")

                # For now, create a test file
                test_file = repo_dir / "hello.txt"
                test_file.write_text("Hello from FastAPI-based Docker container!\n")
                logger.info("Created hello.txt")

                # Commit changes
                await self._commit_changes(repo_dir, f"Implement: {request.task_description}")

                # Push to remote
                await self._push_changes(repo_dir, request.branch_name)

                logger.info("=" * 70)
                logger.info("DEVELOPER AGENT COMPLETED SUCCESSFULLY")
                logger.info("=" * 70)

                self.status = TaskStatus.SUCCESS
                self.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"Developer task failed: {e}", exc_info=True)
            self.error = str(e)
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now()

    async def _authenticate_github(self, token: str):
        """Authenticate GitHub CLI."""
        logger.info("Authenticating with GitHub...")

        try:
            # Authenticate gh CLI
            process = await asyncio.create_subprocess_exec(
                "gh", "auth", "login", "--with-token",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate(input=token.encode())

            if process.returncode != 0:
                logger.error(f"gh auth login failed with exit code {process.returncode}")
                logger.error(f"stdout: {stdout.decode()}")
                logger.error(f"stderr: {stderr.decode()}")
                raise RuntimeError(f"GitHub authentication failed: {stderr.decode()}")

            logger.info("GitHub CLI authenticated")

            # Setup git credential helper
            process = await asyncio.create_subprocess_exec(
                "gh", "auth", "setup-git",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"gh auth setup-git failed: {stderr.decode()}")
                raise RuntimeError(f"Git credential setup failed: {stderr.decode()}")

            logger.info("Git credentials configured")

        except Exception as e:
            logger.error(f"GitHub authentication error: {e}")
            raise

    async def _clone_repository(self, repo_url: str, repo_dir: Path):
        """Clone the repository."""
        logger.info(f"Cloning repository: {repo_url}")

        process = await asyncio.create_subprocess_exec(
            "git", "clone", repo_url, str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Clone failed: {stderr.decode()}")
            raise RuntimeError(f"Repository clone failed: {stderr.decode()}")

        logger.info("Repository cloned successfully")

    async def _setup_branch(self, repo_dir: Path, base_branch: str, branch_name: str):
        """Setup the working branch."""
        logger.info(f"Setting up branch: {branch_name}")

        # Checkout base branch
        process = await asyncio.create_subprocess_exec(
            "git", "checkout", base_branch,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Create and checkout new branch
        process = await asyncio.create_subprocess_exec(
            "git", "checkout", "-b", branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Branch creation failed: {stderr.decode()}")
            raise RuntimeError(f"Branch creation failed: {stderr.decode()}")

        logger.info(f"Branch {branch_name} created and checked out")

    async def _commit_changes(self, repo_dir: Path, message: str):
        """Commit changes."""
        logger.info("Committing changes...")

        # Add all changes
        process = await asyncio.create_subprocess_exec(
            "git", "add", ".",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Commit
        process = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", message,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Commit failed: {stderr.decode()}")
            raise RuntimeError(f"Commit failed: {stderr.decode()}")

        logger.info("Changes committed")

    async def _push_changes(self, repo_dir: Path, branch_name: str):
        """Push changes to remote."""
        logger.info(f"Pushing to remote branch: {branch_name}")

        process = await asyncio.create_subprocess_exec(
            "git", "push", "-u", "origin", branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Push failed: {stderr.decode()}")
            raise RuntimeError(f"Push failed: {stderr.decode()}")

        logger.info("Changes pushed to GitHub successfully!")


if __name__ == "__main__":
    server = DeveloperServer()
    server.run()
