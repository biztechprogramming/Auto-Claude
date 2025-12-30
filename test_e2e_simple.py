#!/usr/bin/env python
"""Simple test to verify E2E infrastructure works."""
import asyncio
import json
from pathlib import Path
import tempfile
import subprocess

async def test_simple_e2e():
    """Test that we can run the workflow."""
    from apps.backend.core.isolation.docker_strategy import DockerIsolationStrategy

    # Create temp repo
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)

        # Initialize git
        subprocess.run(["git", "init"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_dir, check=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_dir, check=True)

        # Create initial commit
        (repo_dir / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_dir, check=True)

        # Create spec
        spec_name = "test-add"
        spec_dir = repo_dir / ".auto-claude" / "specs" / spec_name
        spec_dir.mkdir(parents=True)

        (spec_dir / "spec.md").write_text("""# Test
## Requirements
- Create add.py with add function
## Acceptance Criteria
- add(2,3) returns 5
""")

        plan = {
            "feature": "Test",
            "phases": [{"name": "coding", "description": "Code"}],
            "subtasks": [{"id": "1", "description": "Add function", "status": "pending"}]
        }
        (spec_dir / "implementation_plan.json").write_text(json.dumps(plan))

        # Create strategy
        strategy = DockerIsolationStrategy(
            project_dir=repo_dir,
            base_branch="main",
            repo_url="git@github.com:biztechprogramming/Wexflow.git"
        )

        print(f"Strategy created")
        print(f"Orchestrator: {strategy._orchestrator}")
        print(f"Images dict: {strategy._orchestrator.images}")

        strategy.setup()
        print(f"Setup complete")

        # Try to run pipeline
        print(f"Starting pipeline...")
        result = await strategy.run_pipeline(spec_name=spec_name, plan=plan)
        print(f"Result: {result}")

if __name__ == "__main__":
    asyncio.run(test_simple_e2e())
