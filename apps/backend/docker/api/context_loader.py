"""
Shared context and memory loading utilities for Docker containers.

Provides common functions to load project context, memory files, and other
supporting data that Docker container agents need for autonomous operation.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def safe_format_prompt(template: str, **kwargs) -> str:
    """
    Safely format a prompt template by replacing placeholders.

    Uses simple string replacement instead of str.format() to avoid issues
    with literal curly braces in code examples, JSON, etc.

    Args:
        template: The prompt template string
        **kwargs: Key-value pairs for placeholder replacement

    Returns:
        Formatted prompt with all placeholders replaced
    """
    result = template
    for key, value in kwargs.items():
        placeholder = f"{{{key}}}"
        result = result.replace(placeholder, str(value))
    return result


def load_project_context(repo_dir: Path) -> str:
    """
    Load project context files (project_index.json, context.json, requirements.json).

    Args:
        repo_dir: Path to the repository workspace

    Returns:
        Formatted markdown string with project context
    """
    context_parts = []

    # Try to load from the most recent spec directory
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


def load_memory_content(repo_dir: Path) -> str:
    """
    Load memory files (patterns, gotchas, session insights).

    Args:
        repo_dir: Path to the repository workspace

    Returns:
        Formatted markdown string with memory content
    """
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


def find_spec_dir(repo_dir: Path, spec_name: Optional[str] = None) -> Optional[Path]:
    """
    Find the spec directory for a given spec name or return the most recent one.

    Args:
        repo_dir: Path to the repository workspace
        spec_name: Optional spec name to search for

    Returns:
        Path to the spec directory, or None if not found
    """
    specs_root = repo_dir / ".auto-claude" / "specs"
    if not specs_root.exists():
        return None

    spec_dirs = list(specs_root.glob("*"))
    if not spec_dirs:
        return None

    if spec_name:
        # Try to find exact match
        for spec_dir in spec_dirs:
            if spec_dir.name == spec_name or spec_name in spec_dir.name:
                return spec_dir

    # Return most recent
    return max(spec_dirs, key=lambda p: p.stat().st_mtime)
