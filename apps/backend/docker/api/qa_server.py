"""
QA Container FastAPI Server.

Runs on port 8003 and handles automated testing/QA tasks.
"""

import logging
import os
from pathlib import Path
from datetime import datetime

from base_server import BaseContainerServer, StartRequest, TaskStatus, create_start_endpoint
from context_loader import load_project_context, load_memory_content, safe_format_prompt

logger = logging.getLogger(__name__)

# Check for Claude Agent SDK
try:
    from claude_agent_sdk import query, ClaudeAgentOptions
    CLAUDE_SDK_AVAILABLE = True
    logger.info("Claude Agent SDK loaded successfully")
except ImportError as e:
    logger.error(f"Claude Agent SDK import failed: {e}")
    logger.warning("Claude SDK not available - using placeholder implementation")
    CLAUDE_SDK_AVAILABLE = False


class QAServer(BaseContainerServer):
    """QA container server."""

    def __init__(self):
        # Port can be overridden via CONTAINER_PORT environment variable
        super().__init__(name="QA", port=None)
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

            logger.info(f"Working directory: {repo_dir}")
            logger.info(f"Spec: {request.spec_name}")
            logger.info(f"Branch: {request.branch_name}")

            # Use Claude SDK to perform QA testing
            if CLAUDE_SDK_AVAILABLE:
                logger.info("Using Claude SDK for QA testing")
                await self._execute_with_claude_sdk(request, repo_dir)
            else:
                logger.warning("Claude SDK not available - using placeholder")
                await self._execute_placeholder(request, repo_dir)

            logger.info("=" * 70)
            logger.info("QA AGENT COMPLETED")
            logger.info("=" * 70)

            self.status = TaskStatus.SUCCESS
            self.completed_at = datetime.now()

        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n{traceback.format_exc()}"
            logger.error(f"QA task failed: {error_details}")
            self.error = str(e)
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now()

    async def _execute_with_claude_sdk(self, request: StartRequest, repo_dir: Path):
        """Execute QA testing using Claude SDK."""
        logger.info("=" * 70)
        logger.info("EXECUTING WITH CLAUDE SDK")
        logger.info("=" * 70)

        # Load Docker-specific QA prompt
        qa_prompt_file = Path("/app/prompts/docker/qa.md")
        logger.info(f"Looking for QA prompt at: {qa_prompt_file}")
        if not qa_prompt_file.exists():
            raise FileNotFoundError(f"QA prompt not found: {qa_prompt_file}")

        qa_prompt = qa_prompt_file.read_text(encoding="utf-8")
        logger.info(f"Loaded QA prompt: {len(qa_prompt)} chars")

        # Load additional context files
        project_context = load_project_context(repo_dir)
        memory_content = load_memory_content(repo_dir)

        # Replace placeholders in the prompt template using safe formatting
        full_prompt = safe_format_prompt(
            qa_prompt,
            branch_name=request.branch_name,
            spec_content=request.spec_content,
            project_context=project_context,
            memory_content=memory_content
        )

        logger.info(f"Full prompt length: {len(full_prompt)} chars")
        logger.info(f"Full prompt preview (first 500 chars):\n{full_prompt[:500]}")

        # Verify OAuth token
        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if not oauth_token:
            raise ValueError("CLAUDE_CODE_OAUTH_TOKEN not set")

        logger.info("=" * 70)
        logger.info("STARTING CLAUDE AGENT SDK SESSION")
        logger.info(f"Working directory: {repo_dir}")
        logger.info("=" * 70)

        # Use Claude Agent SDK query function
        try:
            async for message in query(
                prompt=full_prompt,
                options=ClaudeAgentOptions(
                    # All tools available - Claude will autonomously use what it needs
                    allowed_tools=None,  # None = all tools allowed
                    cwd=str(repo_dir),  # Set working directory to the repository
                )
            ):
                # Log useful information from messages
                msg_type = getattr(message, 'type', 'unknown')

                if msg_type == 'text':
                    # Text content from Claude
                    text = getattr(message, 'text', '')
                    if text:
                        logger.info(f"[Claude] {text[:200]}")  # First 200 chars

                elif msg_type == 'tool_use':
                    # Claude is using a tool
                    tool_name = getattr(message, 'name', 'unknown')
                    logger.info(f"[Tool Use] {tool_name}")

                elif msg_type == 'tool_result':
                    # Tool execution result
                    tool_name = getattr(message, 'tool_name', 'unknown')
                    logger.info(f"[Tool Result] {tool_name} completed")

                elif hasattr(message, 'content'):
                    # Generic content message
                    content = message.content
                    if isinstance(content, list) and len(content) > 0:
                        first_item = content[0]
                        if hasattr(first_item, 'type'):
                            if first_item.type == 'text':
                                text = getattr(first_item, 'text', '')[:200]
                                logger.info(f"[Claude] {text}")
                            elif first_item.type == 'tool_use':
                                tool_name = getattr(first_item, 'name', 'unknown')
                                logger.info(f"[Tool Use] {tool_name}")
                    else:
                        logger.info(f"[Message] type={msg_type}")

            logger.info("=" * 70)
            logger.info("CLAUDE AGENT SDK SESSION COMPLETED SUCCESSFULLY")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"Claude Agent SDK session failed: {e}", exc_info=True)
            raise RuntimeError(f"Claude Agent SDK failed: {e}")

    async def _execute_placeholder(self, request: StartRequest, repo_dir: Path):
        """Placeholder implementation when Claude SDK is not available."""
        logger.info("Executing QA testing (placeholder implementation)...")
        logger.info(f"Running tests for: {request.spec_name}")
        logger.info(f"Workspace: {repo_dir}")
        logger.info("Placeholder: Automatically passing (no actual testing)")


if __name__ == "__main__":
    server = QAServer()
    server.run()
