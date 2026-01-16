#!/usr/bin/env python3
"""
Test script to launch developer container and clone current repository.

This tests:
1. ImageBuilder can build the developer image
2. ContainerLifecycleManager can start a container
3. Container's FastAPI server starts correctly
4. Container can clone a repository
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

# Add apps/backend to path
sys.path.insert(0, str(Path(__file__).parent))

from core.isolation.docker.image_builder import ImageBuilder
from core.isolation.docker.container_manager import ContainerLifecycleManager, ContainerConfig
from core.isolation.base import ContainerRole
from core.isolation.container_client import ContainerClient, ContainerConfig as ClientConfig


def get_current_repo_url() -> str:
    """Get the current repository's URL."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_current_branch() -> str:
    """Get the current branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


async def test_container_clone():
    """Test launching container and cloning repository."""
    print("=" * 70)
    print("TESTING CONTAINER LAUNCH AND REPOSITORY CLONE")
    print("=" * 70)
    print()

    # Step 1: Get current repository info
    print("Step 1: Detecting current repository...")
    repo_url = get_current_repo_url()
    branch_name = get_current_branch()
    print(f"  Repository: {repo_url}")
    print(f"  Branch: {branch_name}")
    print()

    # Step 2: Build developer image if needed
    print("Step 2: Ensuring developer image is built...")
    builder = ImageBuilder()
    developer_image = builder.DEFAULT_IMAGE_DEVELOPER

    if not builder.image_exists(developer_image):
        print(f"  Building {developer_image}...")
        builder.build_all_images(force=False)
    else:
        print(f"  {developer_image} already exists")
    print()

    # Step 3: Prepare container configuration
    print("Step 3: Preparing container configuration...")
    container_name = "auto-claude-test-developer"
    port = 8001

    # Get environment variables
    env_vars = {
        "CLAUDE_CODE_OAUTH_TOKEN": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
        "GH_TOKEN": os.environ.get("GH_TOKEN", ""),
    }

    if not env_vars["GH_TOKEN"]:
        print("  WARNING: GH_TOKEN not set - clone may fail")

    print(f"  Container name: {container_name}")
    print(f"  Port: {port}")
    print()

    # Step 4: Start the container
    print("Step 4: Starting developer container...")
    manager = ContainerLifecycleManager()

    config = ContainerConfig(
        name=container_name,
        image=developer_image,
        port=port,
        env_vars=env_vars,
    )

    try:
        container_id = manager.start_container(config)
        print(f"  Container started: {container_id[:12]}")
        print()

        # Step 5: Wait for FastAPI server to be ready
        print("Step 5: Waiting for FastAPI server to be ready...")
        client_config = ClientConfig(
            name=container_name,
            image=developer_image,
            port=port,
            env_vars=env_vars,
        )
        client = ContainerClient(client_config)

        if not client.wait_for_ready(timeout=30):
            raise RuntimeError("FastAPI server did not become ready")
        print("  FastAPI server is ready!")
        print()

        # Step 6: Clone the repository
        print("Step 6: Cloning repository in container...")
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            response = await http_client.post(
                f"http://localhost:{port}/clone",
                json={
                    "repo_url": repo_url,
                    "branch_name": branch_name,
                }
            )

            if response.status_code == 200:
                result = response.json()
                print(f"  Clone successful!")
                print(f"  Status: {result.get('status')}")
                print(f"  Workspace: {result.get('workspace')}")
                print()

                # Step 7: Verify by checking logs
                print("Step 7: Checking container logs...")
                logs = await client.get_logs(count=50)
                print(f"  Retrieved {len(logs)} log entries")

                # Show recent logs
                print("\n  Recent logs:")
                for log in logs[-10:]:
                    print(f"    [{log['level']}] {log['message']}")
                print()

                print("=" * 70)
                print("✅ TEST PASSED!")
                print("=" * 70)
                print()
                print("Summary:")
                print("  - Developer image built successfully")
                print("  - Container launched and FastAPI server started")
                print(f"  - Repository cloned: {repo_url}")
                print(f"  - Branch checked out: {branch_name}")
                print(f"  - Container ID: {container_id[:12]}")
                print()
                print(f"To stop the container, run:")
                print(f"  docker stop {container_name}")
                print(f"  docker rm {container_name}")

                return True
            else:
                print(f"  ❌ Clone failed with status {response.status_code}")
                print(f"  Response: {response.text}")
                return False

    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

        # Cleanup on failure
        print("\nCleaning up container...")
        manager.cleanup_container(container_name)
        return False


if __name__ == "__main__":
    result = asyncio.run(test_container_clone())
    sys.exit(0 if result else 1)
