"""
Developer Container FastAPI Server.

Runs on port 8001 and handles development tasks.
"""

import logging
import os
from pathlib import Path
from datetime import datetime

from base_server import BaseContainerServer, StartRequest, TaskStatus, create_start_endpoint

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


class DeveloperServer(BaseContainerServer):
    """Developer container server."""

    def __init__(self):
        super().__init__(name="Developer", port=8001)
        create_start_endpoint(self)

    async def _run_task(self, request: StartRequest):
        """Execute development task using Claude SDK."""
        try:
            logger.info("=" * 70)
            logger.info("DEVELOPER AGENT STARTING")
            logger.info("=" * 70)

            # Workspace should already be setup via /clone endpoint
            repo_dir = Path("/workspace")

            if not repo_dir.exists() or not (repo_dir / ".git").exists():
                raise RuntimeError("Workspace not initialized. Call /clone first.")

            logger.info(f"Working directory: {repo_dir}")
            logger.info(f"Spec: {request.spec_name}")
            logger.info(f"Spec content length: {len(request.spec_content)} chars")
            logger.info(f"Spec content preview (first 200 chars): {request.spec_content[:200]}")

            # Create and checkout the feature branch
            logger.info(f"Creating branch: {request.branch_name}")
            await self._checkout_branch(repo_dir, request.branch_name)

            # Use Claude SDK to implement the spec
            logger.info(f"CLAUDE_SDK_AVAILABLE = {CLAUDE_SDK_AVAILABLE}")
            if CLAUDE_SDK_AVAILABLE:
                logger.info("Using Claude SDK implementation")
                await self._execute_with_claude_sdk(request, repo_dir)
            else:
                # Fallback: placeholder implementation
                logger.warning("Claude SDK not available - using placeholder")
                logger.warning("This will only modify README.md and not implement the spec!")
                await self._execute_placeholder(request, repo_dir)

            # Commit changes
            commit_message = f"feat: Implement {request.spec_name}\n\n{self._get_commit_body(request)}"
            await self._commit_changes(repo_dir, commit_message)
            logger.info("Changes committed locally")

            # Push the new branch to remote
            await self._push_changes(repo_dir, request.branch_name)
            logger.info(f"Changes pushed to {request.branch_name}")

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

    async def _execute_with_claude_sdk(self, request: StartRequest, repo_dir: Path):
        """Execute task using Claude SDK."""
        logger.info("=" * 70)
        logger.info("EXECUTING WITH CLAUDE SDK")
        logger.info("=" * 70)

        # Load Docker-specific developer prompt
        developer_prompt_file = Path("/app/prompts/docker/developer.md")
        logger.info(f"Looking for developer prompt at: {developer_prompt_file}")
        if not developer_prompt_file.exists():
            raise FileNotFoundError(f"Developer prompt not found: {developer_prompt_file}")

        developer_prompt = developer_prompt_file.read_text(encoding="utf-8")
        logger.info(f"Loaded developer prompt: {len(developer_prompt)} chars")

        # Load additional context files
        project_context = self._load_project_context(repo_dir)
        memory_content = self._load_memory_content(repo_dir)

        # Replace placeholders in the prompt template
        full_prompt = developer_prompt.format(
            branch_name=request.branch_name,
            spec_content=request.spec_content,
            project_context=project_context,
            memory_content=memory_content,
            feedback_comments=request.feedback_comments or "No feedback from previous iterations."
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
        # It returns an async generator that yields messages
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

    def _load_project_context(self, repo_dir: Path) -> str:
        """Load project context files (project_index.json, context.json, requirements.json)."""
        import json

        context_parts = []

        # Try to load project_index.json
        spec_dirs = list((repo_dir / ".auto-claude" / "specs").glob("*")) if (repo_dir / ".auto-claude" / "specs").exists() else []
        if spec_dirs:
            # Use the most recent spec directory
            spec_dir = max(spec_dirs, key=lambda p: p.stat().st_mtime)

            # Load project_index.json
            project_index_file = spec_dir / "project_index.json"
            if project_index_file.exists():
                try:
                    project_index = json.loads(project_index_file.read_text(encoding="utf-8"))
                    context_parts.append(f"## Project Index\n\n```json\n{json.dumps(project_index, indent=2)}\n```")
                    logger.info(f"Loaded project index from {project_index_file}")
                except Exception as e:
                    logger.warning(f"Failed to load project_index.json: {e}")

            # Load context.json
            context_file = spec_dir / "context.json"
            if context_file.exists():
                try:
                    context_data = json.loads(context_file.read_text(encoding="utf-8"))
                    context_parts.append(f"## Codebase Context\n\n```json\n{json.dumps(context_data, indent=2)}\n```")
                    logger.info(f"Loaded context from {context_file}")
                except Exception as e:
                    logger.warning(f"Failed to load context.json: {e}")

            # Load requirements.json
            requirements_file = spec_dir / "requirements.json"
            if requirements_file.exists():
                try:
                    requirements_data = json.loads(requirements_file.read_text(encoding="utf-8"))
                    context_parts.append(f"## Requirements\n\n```json\n{json.dumps(requirements_data, indent=2)}\n```")
                    logger.info(f"Loaded requirements from {requirements_file}")
                except Exception as e:
                    logger.warning(f"Failed to load requirements.json: {e}")

        if not context_parts:
            return "No project context available."

        return "\n\n".join(context_parts)

    def _load_memory_content(self, repo_dir: Path) -> str:
        """Load memory files (patterns, gotchas, session insights)."""
        memory_parts = []

        # Find the spec directory
        spec_dirs = list((repo_dir / ".auto-claude" / "specs").glob("*")) if (repo_dir / ".auto-claude" / "specs").exists() else []
        if spec_dirs:
            spec_dir = max(spec_dirs, key=lambda p: p.stat().st_mtime)
            memory_dir = spec_dir / "memory"

            if memory_dir.exists():
                # Load patterns.md
                patterns_file = memory_dir / "patterns.md"
                if patterns_file.exists():
                    try:
                        patterns = patterns_file.read_text(encoding="utf-8")
                        memory_parts.append(f"## Code Patterns\n\n{patterns}")
                        logger.info(f"Loaded patterns from {patterns_file}")
                    except Exception as e:
                        logger.warning(f"Failed to load patterns.md: {e}")

                # Load gotchas.md
                gotchas_file = memory_dir / "gotchas.md"
                if gotchas_file.exists():
                    try:
                        gotchas = gotchas_file.read_text(encoding="utf-8")
                        memory_parts.append(f"## Known Gotchas\n\n{gotchas}")
                        logger.info(f"Loaded gotchas from {gotchas_file}")
                    except Exception as e:
                        logger.warning(f"Failed to load gotchas.md: {e}")

                # Load codebase_map.json
                codebase_map_file = memory_dir / "codebase_map.json"
                if codebase_map_file.exists():
                    try:
                        import json
                        codebase_map = json.loads(codebase_map_file.read_text(encoding="utf-8"))
                        memory_parts.append(f"## Codebase Map\n\n```json\n{json.dumps(codebase_map, indent=2)}\n```")
                        logger.info(f"Loaded codebase map from {codebase_map_file}")
                    except Exception as e:
                        logger.warning(f"Failed to load codebase_map.json: {e}")

                # Load recent session insights (last 3)
                session_insights_dir = memory_dir / "session_insights"
                if session_insights_dir.exists():
                    insight_files = sorted(session_insights_dir.glob("session_*.json"), reverse=True)[:3]
                    if insight_files:
                        import json
                        insights_content = []
                        for insight_file in insight_files:
                            try:
                                insight = json.loads(insight_file.read_text(encoding="utf-8"))
                                insights_content.append(json.dumps(insight, indent=2))
                            except Exception as e:
                                logger.warning(f"Failed to load {insight_file}: {e}")
                        if insights_content:
                            memory_parts.append(f"## Recent Session Insights\n\n```json\n{chr(10).join(insights_content)}\n```")
                            logger.info(f"Loaded {len(insights_content)} session insights")

        if not memory_parts:
            return "No memory files available yet (first session)."

        return "\n\n".join(memory_parts)

    async def _execute_placeholder(self, request: StartRequest, repo_dir: Path):
        """Placeholder implementation when Claude SDK is not available."""
        logger.info("Executing task (placeholder implementation)...")

        # Example: Modify README.md
        readme = repo_dir / "README.md"
        if readme.exists():
            content = readme.read_text()
            task_desc = request.task_description or request.spec_name
            content += f"\n\n## Container Test\nModified by containerized agent: {task_desc}\n"
            readme.write_text(content)
            logger.info("Modified README.md")

    def _get_commit_body(self, request: StartRequest) -> str:
        """Generate commit message body."""
        body = f"Specification: {request.spec_name}"
        if request.feedback_comments:
            body += "\n\nAddresses feedback from evaluator/QA"
        return body


if __name__ == "__main__":
    server = DeveloperServer()
    server.run()
