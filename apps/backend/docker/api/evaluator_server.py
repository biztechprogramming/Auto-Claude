"""
Evaluator Container FastAPI Server.

Runs on port 8002 and handles code review/evaluation tasks.
"""

import logging
from datetime import datetime

from base_server import BaseContainerServer, StartRequest, TaskStatus, create_start_endpoint

logger = logging.getLogger(__name__)


class EvaluatorServer(BaseContainerServer):
    """Evaluator container server."""

    def __init__(self):
        super().__init__(name="Evaluator", port=8002)
        create_start_endpoint(self)

    async def _run_task(self, request: StartRequest):
        """Execute code evaluation task."""
        try:
            logger.info("=" * 70)
            logger.info("EVALUATOR AGENT STARTING")
            logger.info("=" * 70)

            # TODO: Implement actual code review logic
            logger.info(f"Reviewing code for: {request.spec_name}")
            logger.info(f"Branch: {request.branch_name}")

            # Placeholder: Mark as success for now
            logger.info("Code review completed successfully")

            logger.info("=" * 70)
            logger.info("EVALUATOR AGENT COMPLETED")
            logger.info("=" * 70)

            self.status = TaskStatus.SUCCESS
            self.completed_at = datetime.now()

        except Exception as e:
            logger.error(f"Evaluator task failed: {e}", exc_info=True)
            self.error = str(e)
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now()


if __name__ == "__main__":
    server = EvaluatorServer()
    server.run()
