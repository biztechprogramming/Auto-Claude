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

from core.isolation.docker.image_builder import ImageBuilder


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

    # Create image builder (no unnecessary parameters!)
    builder = ImageBuilder()

    # Force rebuild all images
    try:
        builder.build_all_images(force=True)
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
