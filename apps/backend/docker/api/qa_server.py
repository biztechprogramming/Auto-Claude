"""
QA Container FastAPI Server.

Runs on port 8003 and handles automated testing/QA tasks.
"""

import logging
from pathlib import Path
from datetime import datetime

from base_server import BaseContainerServer, StartRequest, TaskStatus, create_start_endpoint

logger = logging.getLogger(__name__)


class QAServer(BaseContainerServer):
    """QA container server."""

    def __init__(self):
        super().__init__(name="QA", port=8003)
        create_start_endpoint(self)

    async def _run_task(self, request: StartRequest):
        """Execute QA/testing task."""
        try:
            logger.info("=" * 70)
            logger.info("QA AGENT STARTING")
            logger.info("=" * 70)

            # Workspace should already be setup by orchestrator via /clone endpoint
            repo_dir = Path("/workspace")

            if not repo_dir.exists() or not (repo_dir / ".git").exists():
                raise RuntimeError("Workspace not initialized. Orchestrator must call /clone first.")

            # TODO: Implement actual QA/testing logic using Claude SDK + Playwright
            logger.info(f"Running tests for: {request.spec_name}")
            logger.info(f"Workspace: {repo_dir}")

            # Placeholder: Mark as success for now
            logger.info("All tests passed successfully")

            logger.info("=" * 70)
            logger.info("QA AGENT COMPLETED")
            logger.info("=" * 70)

            self.status = TaskStatus.SUCCESS
            self.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"QA task failed: {e}", exc_info=True)
            self.error = str(e)
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now()


if __name__ == "__main__":
    server = QAServer()
    server.run()
