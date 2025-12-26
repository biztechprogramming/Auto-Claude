"""
Developer Container FastAPI Server.

Runs on port 8001 and handles development tasks.
"""

import logging
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

            # Workspace should already be setup by orchestrator via /clone endpoint
            repo_dir = Path("/workspace")

            if not repo_dir.exists() or not (repo_dir / ".git").exists():
                raise RuntimeError("Workspace not initialized. Orchestrator must call /clone first.")

            # Run implementation (TODO: integrate with Claude SDK)
            logger.info("Starting implementation...")
            logger.info(f"Task: {request.task_description}")
            logger.info(f"Working directory: {repo_dir}")

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


if __name__ == "__main__":
    server = DeveloperServer()
    server.run()
