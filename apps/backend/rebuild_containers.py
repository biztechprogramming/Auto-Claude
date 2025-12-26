#!/usr/bin/env python3
"""
Rebuild Docker Containers Script

Forces a rebuild of all Auto-Claude Docker containers.
This is useful when you've made changes to:
- Dockerfiles
- FastAPI server code
- Prompt files
- Base dependencies
"""

import sys
from pathlib import Path

# Add apps/backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.isolation.orchestrator import DockerOrchestrator
from core.isolation.base import ContainerRole


def main():
    """Force rebuild all Docker containers."""
    print("=" * 70)
    print("REBUILDING ALL DOCKER CONTAINERS")
    print("=" * 70)
    print()
    print("This will rebuild:")
    print("  - Base image (auto-claude-base:latest)")
    print("  - Developer container (auto-claude-dev:latest)")
    print("  - Evaluator container (auto-claude-eval:latest)")
    print("  - QA container (auto-claude-qa:latest)")
    print()

    # Create orchestrator with minimal config (just for building images)
    orchestrator = DockerOrchestrator(
        project_dir=Path.cwd(),
        base_branch="main",
        repo_url="",  # Not needed for building
        images={
            ContainerRole.DEVELOPER: "auto-claude-dev:latest",
            ContainerRole.EVALUATOR: "auto-claude-eval:latest",
            ContainerRole.QA: "auto-claude-qa:latest",
        },
    )

    # Force rebuild all images
    try:
        orchestrator.build_images(force=True)
        print()
        print("=" * 70)
        print("REBUILD COMPLETE!")
        print("=" * 70)
        print()
        print("All Docker containers have been rebuilt successfully.")
        print("You can now run your specs with the updated containers.")
        return 0
    except Exception as e:
        print()
        print("=" * 70)
        print("REBUILD FAILED!")
        print("=" * 70)
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
