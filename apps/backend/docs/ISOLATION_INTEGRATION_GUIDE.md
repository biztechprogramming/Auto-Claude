# Isolation Integration Guide

## Overview

### What is Isolation?

Auto Claude's isolation system provides secure, sandboxed environments for building features without affecting your main project directory. It allows AI agents to implement code changes in controlled environments with rollback capabilities.

### Why Isolation?

- **Safety**: Changes happen in isolated environments, never directly in your working directory
- **Rollback**: Easily discard changes if they don't work out
- **Security**: Multi-layer protection (OS sandbox, filesystem permissions, command allowlisting)
- **Parallelization**: Future support for parallel feature development
- **Code Review**: Review changes before merging them into your project

### Two Isolation Modes

1. **Worktree Mode (Default)**: Uses Git worktrees for lightweight, local isolation
   - Runs on your machine with security hooks
   - Fast and simple
   - No Docker required
   - Perfect for individual development

2. **Docker Mode**: Uses containers for full OS-level isolation
   - Multi-container pipeline (developer → evaluator → qa)
   - Maximum isolation and security
   - Reproducible builds
   - Ideal for CI/CD and team environments

---

## Quick Start

### Basic Usage (Worktree Mode)

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory

# Create isolation strategy (defaults to worktree)
project_dir = Path("/path/to/your/project")
strategy = IsolationFactory.create(project_dir)

# Initialize
strategy.setup()

# Create isolated environment for a spec
env = strategy.create_environment("feature-auth")
print(f"Working in: {env.working_dir}")
print(f"Branch: {env.branch_name}")

# Run the build pipeline
plan = {...}  # Your implementation plan
success = await strategy.run_pipeline("feature-auth", plan)

# Review changes
changed_files = strategy.get_changed_files("feature-auth")
for status, path in changed_files:
    print(f"{status}\t{path}")

# Merge if satisfied
if success:
    strategy.merge_changes("feature-auth", delete_after=True)
else:
    strategy.remove_environment("feature-auth")
```

### Switching to Docker Mode

```bash
# Set environment variable
export ISOLATION_METHOD=docker

# Or in your .env file
echo "ISOLATION_METHOD=docker" >> apps/backend/.env
```

```python
# Same code works with Docker!
strategy = IsolationFactory.create(project_dir)  # Reads ISOLATION_METHOD
strategy.setup()  # Builds Docker images if needed
# ... rest is identical
```

---

## Code Examples

### Example 1: Worktree Mode with Custom Permissions

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory

# Create worktree strategy with permission overrides
strategy = IsolationFactory.create(
    project_dir=Path("/workspace/my-project"),
    base_branch="develop",
    method="worktree",
    permission_overrides={
        "permissions": {
            "allow": ["Bash(npm *)"],  # Additional allowed commands
            "extend_allow": True,  # Extend default allow list
        }
    }
)

strategy.setup()

# Create environment
env = strategy.create_environment("add-user-auth")

# Check permissions being used
perms = strategy.get_permission_settings()
print(f"Allowed commands: {perms['permissions']['allow']}")

# Run pipeline
plan = {
    "subtasks": [
        {"id": 1, "description": "Create User model", "status": "pending"},
        {"id": 2, "description": "Add auth endpoints", "status": "pending"},
        {"id": 3, "description": "Write tests", "status": "pending"},
    ]
}

success = await strategy.run_pipeline("add-user-auth", plan)

if success:
    # Merge without deleting branch (keep for review)
    strategy.merge_changes("add-user-auth", delete_after=False)
else:
    # Clean up failed build
    strategy.remove_environment("add-user-auth", cleanup_branch=True)
```

### Example 2: Docker Mode with Custom Images

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory

# Create Docker strategy with custom configuration
strategy = IsolationFactory.create(
    project_dir=Path("/workspace/my-project"),
    base_branch="main",
    method="docker",
    # Docker-specific kwargs
    image_developer="my-company/auto-claude-dev:v2",
    image_evaluator="my-company/auto-claude-eval:v2",
    image_qa="my-company/auto-claude-qa:v2",
    memory_limit="8g",
    cpu_shares="2048",
    repo_url="https://github.com/mycompany/myrepo.git",
    database_url="postgresql://user:pass@db:5432/mydb",
    max_feedback_iterations=5,
)

# Check Docker availability
if not IsolationFactory.is_docker_available():
    print("Docker not available, falling back to worktree")
    strategy = IsolationFactory.create(project_dir, method="worktree")

strategy.setup()  # Builds images if needed

# Create environment (creates branch)
env = strategy.create_environment("optimize-queries")

# Run multi-container pipeline
success = await strategy.run_pipeline(
    spec_name="optimize-queries",
    plan=plan,
    on_status_change=lambda spec, status, msg: print(f"{spec}: {status} - {msg}")
)

# Docker pipeline runs: developer → evaluator → qa with feedback loops
# Returns True only if all checks pass
```

### Example 3: Environment Management

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory

strategy = IsolationFactory.create(Path("/workspace/my-project"))
strategy.setup()

# List all active environments
envs = strategy.list_environments()
for env in envs:
    print(f"Spec: {env.spec_name}")
    print(f"  Branch: {env.branch_name}")
    print(f"  Dir: {env.working_dir}")
    print(f"  Active: {env.is_active}")

    # Show changed files
    files = strategy.get_changed_files(env.spec_name)
    print(f"  Changes: {len(files)} files")
    for status, path in files:
        print(f"    {status}\t{path}")
    print()

# Get or create (idempotent)
env = strategy.get_or_create_environment("feature-x")
print(f"Environment exists: {env is not None}")

# Clean up old environments
for env in envs:
    if not env.is_active:
        strategy.remove_environment(env.spec_name, cleanup_branch=True)
```

### Example 4: Error Handling and Feedback

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory
from core.isolation.base import ContainerResult, FeedbackComment

async def build_with_status_tracking(spec_name: str, plan: dict):
    """Build a spec with detailed status tracking."""
    strategy = IsolationFactory.create(Path("/workspace"))
    strategy.setup()

    # Status callback for monitoring
    def on_status_change(spec: str, status: str, message: str = ""):
        print(f"[{spec}] {status}: {message}")

    try:
        # Run pipeline with status tracking
        success = await strategy.run_pipeline(
            spec_name=spec_name,
            plan=plan,
            on_status_change=on_status_change,
        )

        if success:
            print(f"✓ Build succeeded!")

            # Review changes before merging
            files = strategy.get_changed_files(spec_name)
            print(f"Changed {len(files)} files:")
            for status, path in files:
                print(f"  {status}\t{path}")

            # Ask user for confirmation
            response = input("Merge changes? [y/N]: ")
            if response.lower() == 'y':
                if strategy.merge_changes(spec_name, delete_after=True):
                    print("✓ Changes merged successfully")
                else:
                    print("✗ Merge failed")
            else:
                print("Merge skipped. Environment preserved for review.")
        else:
            print(f"✗ Build failed")
            # Environment preserved for debugging

    except Exception as e:
        print(f"✗ Error: {e}")
        # Clean up on unexpected error
        strategy.remove_environment(spec_name, cleanup_branch=False)
        raise

# Usage
plan = {"subtasks": [...]}
await build_with_status_tracking("feature-auth", plan)
```

---

## Integration with Existing Code

### How Worktree Strategy Wraps WorktreeManager

The `WorktreeIsolationStrategy` is a thin wrapper around the existing `WorktreeManager`:

```python
# core/isolation/worktree_strategy.py

class WorktreeIsolationStrategy(IsolationStrategy):
    def __init__(self, project_dir: Path, base_branch: Optional[str] = None):
        super().__init__(project_dir, base_branch)
        # Delegates to existing WorktreeManager
        self._manager = WorktreeManager(project_dir, base_branch)

    def create_environment(self, spec_name: str) -> IsolationInfo:
        # Calls existing method
        info = self._manager.create_worktree(spec_name)

        # Converts to common IsolationInfo format
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )
```

**Key points:**
- No changes to existing `WorktreeManager` code
- Full backward compatibility
- Same security model (sandbox, permissions, bash_security_hook)
- Unified interface allows switching to Docker without code changes

### Optional: Integrating into build_commands.py

You can optionally migrate your build commands to use the new isolation system:

```python
# Before (direct WorktreeManager usage)
from worktree import WorktreeManager

manager = WorktreeManager(project_dir)
manager.create_worktree(spec_name)
# ... manual agent orchestration ...
manager.merge_worktree(spec_name)

# After (IsolationFactory)
from core.isolation.factory import IsolationFactory

strategy = IsolationFactory.create(project_dir)  # Reads ISOLATION_METHOD
strategy.setup()
env = strategy.create_environment(spec_name)
await strategy.run_pipeline(spec_name, plan)  # Handles full pipeline
strategy.merge_changes(spec_name, delete_after=True)
```

**Benefits of migration:**
- Environment variable-based mode switching
- Docker support without code changes
- Unified interface for all isolation modes
- Built-in pipeline orchestration

**Migration is optional:** Existing code using `WorktreeManager` directly continues to work.

---

## Configuration

### Environment Variables

From `.env.example`:

```bash
# =============================================================================
# ISOLATION METHOD (OPTIONAL)
# =============================================================================
# Choose how Auto-Claude isolates code changes during builds.
#
# Options:
#   - worktree (default): Uses Git worktrees, runs locally with security hooks
#   - docker: Uses Docker containers for full OS-level isolation
#
ISOLATION_METHOD=worktree

# =============================================================================
# WORKTREE SETTINGS (only used if ISOLATION_METHOD=worktree)
# =============================================================================

# Permission overrides (JSON format, optional)
# Example: {"permissions": {"allow": ["Bash(npm *)"], "extend_allow": true}}
WORKTREE_PERMISSION_OVERRIDES={}

# =============================================================================
# DOCKER SETTINGS (only used if ISOLATION_METHOD=docker)
# =============================================================================

# Container images (defaults shown)
DOCKER_IMAGE_DEVELOPER=auto-claude-dev:latest
DOCKER_IMAGE_EVALUATOR=auto-claude-eval:latest
DOCKER_IMAGE_QA=auto-claude-qa:latest

# Resource limits
DOCKER_MEMORY_LIMIT=4g
DOCKER_CPU_SHARES=1024

# Repository URL (auto-detected from git remote if not set)
REPO_URL=https://github.com/user/repo.git

# Database connection (read-only access for containers)
DATABASE_URL=postgresql://user:pass@host:5432/db

# Maximum feedback iterations before failing
MAX_FEEDBACK_ITERATIONS=3
```

### Docker Requirements

For Docker mode, you need:

1. **Docker Installed**
   ```bash
   docker --version
   # Docker version 20.10.0 or higher
   ```

2. **Docker Images Built**
   ```bash
   cd apps/backend
   python -c "
   from pathlib import Path
   from core.isolation.factory import IsolationFactory
   strategy = IsolationFactory.create(Path('.'), method='docker')
   strategy.setup()  # Builds images
   "
   ```

3. **Git Remote Configured**
   ```bash
   git remote get-url origin
   # Should return your repository URL
   ```

4. **OAuth Token Set**
   ```bash
   # In apps/backend/.env
   CLAUDE_CODE_OAUTH_TOKEN=your-token-here
   ```

### Dockerfile Structure

Auto Claude expects these Dockerfiles in `apps/backend/docker/`:

```
apps/backend/docker/
├── Dockerfile.base          # Base image (shared dependencies)
├── Dockerfile.developer     # Developer agent container
├── Dockerfile.evaluator     # Code review agent container
└── Dockerfile.qa            # QA testing agent container
```

Each container includes:
- Python 3.12+
- Claude SDK
- Git
- Project-specific dependencies
- Agent scripts in `/scripts/`

---

## Troubleshooting

### Common Issues

#### 1. Docker Not Available

**Error:**
```
RuntimeError: Docker is not available. Please install Docker or use worktree isolation.
```

**Solution:**
```python
# Check Docker availability before using
if IsolationFactory.is_docker_available():
    strategy = IsolationFactory.create(project_dir, method="docker")
else:
    print("Docker not available, using worktree mode")
    strategy = IsolationFactory.create(project_dir, method="worktree")
```

Or set fallback in environment:
```bash
# Auto-fallback to worktree if Docker unavailable
export ISOLATION_METHOD=worktree
```

#### 2. Permission Denied Errors (Worktree)

**Error:**
```
BashCommandBlocked: Command 'rm -rf node_modules' blocked by security policy
```

**Solution:**
Add permission override:
```python
strategy = IsolationFactory.create(
    project_dir,
    permission_overrides={
        "permissions": {
            "allow": ["Bash(rm -rf node_modules)"],
            "extend_allow": True,
        }
    }
)
```

Or in `.env`:
```bash
WORKTREE_PERMISSION_OVERRIDES='{"permissions": {"allow": ["Bash(rm -rf node_modules)"], "extend_allow": true}}'
```

#### 3. Docker Image Build Failures

**Error:**
```
Failed to build Docker images
```

**Solution:**
1. Ensure Dockerfiles exist in `apps/backend/docker/`
2. Check Docker daemon is running: `docker ps`
3. Build manually to see detailed errors:
   ```bash
   cd apps/backend/docker
   docker build -f Dockerfile.base -t auto-claude-base:latest .
   docker build -f Dockerfile.developer -t auto-claude-dev:latest .
   ```

#### 4. Git Remote Not Found (Docker)

**Error:**
```
RuntimeError: Could not detect repository URL. Set REPO_URL env var.
```

**Solution:**
```bash
# Set repository URL in .env
export REPO_URL=https://github.com/youruser/yourrepo.git
```

Or pass directly:
```python
strategy = IsolationFactory.create(
    project_dir,
    method="docker",
    repo_url="https://github.com/youruser/yourrepo.git"
)
```

#### 5. Max Iterations Reached (Docker)

**Error:**
```
Max iterations (3) reached
```

**Meaning:** The developer → evaluator → qa feedback loop ran 3 times without success.

**Solutions:**
1. Increase max iterations:
   ```bash
   export MAX_FEEDBACK_ITERATIONS=5
   ```

2. Or in code:
   ```python
   strategy = IsolationFactory.create(
       project_dir,
       method="docker",
       max_feedback_iterations=5
   )
   ```

3. Review feedback comments to understand what's failing:
   ```python
   # Docker orchestrator logs show feedback
   # Check container logs for details
   ```

#### 6. Worktree Already Exists

**Error:**
```
fatal: 'auto-claude/feature-x' already exists
```

**Solution:**
```python
# Get existing environment instead
env = strategy.get_environment("feature-x")
if env:
    print(f"Environment exists: {env.branch_name}")
else:
    env = strategy.create_environment("feature-x")

# Or use get_or_create (idempotent)
env = strategy.get_or_create_environment("feature-x")
```

#### 7. Merge Conflicts

**Error:**
```
Merge failed: CONFLICT (content): Merge conflict in src/app.py
```

**Solution:**
```python
# Merge returns False on conflict
success = strategy.merge_changes("feature-x")
if not success:
    print("Merge conflict detected. Resolve manually:")

    # For worktree mode
    env = strategy.get_environment("feature-x")
    print(f"1. cd {env.working_dir}")
    print(f"2. Resolve conflicts in your editor")
    print(f"3. git add .")
    print(f"4. git commit")
    print(f"5. Re-run merge")
```

---

## Advanced Usage

### Custom Status Callbacks

Monitor pipeline progress in real-time:

```python
async def build_with_ui_updates(spec_name: str, plan: dict):
    """Build with live UI status updates."""
    strategy = IsolationFactory.create(Path("/workspace"))

    # Status callback
    def update_status(spec: str, status: str, message: str = ""):
        # Update your UI here
        ui.update_spec_status(spec, status, message)

        # Log to file
        with open(f".auto-claude/logs/{spec}.log", "a") as f:
            f.write(f"[{status}] {message}\n")

    await strategy.run_pipeline(
        spec_name=spec_name,
        plan=plan,
        on_status_change=update_status
    )
```

### Parallel Builds (Future)

While not yet implemented, the interface supports future parallel execution:

```python
# Future capability
async def build_multiple_specs(specs: list[dict]):
    """Build multiple specs in parallel."""
    strategy = IsolationFactory.create(Path("/workspace"))
    strategy.setup()

    tasks = [
        strategy.run_pipeline(spec["name"], spec["plan"])
        for spec in specs
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for spec, result in zip(specs, results):
        if isinstance(result, Exception):
            print(f"✗ {spec['name']} failed: {result}")
        elif result:
            print(f"✓ {spec['name']} succeeded")
        else:
            print(f"✗ {spec['name']} failed")
```

### Inspecting Docker Containers

For debugging Docker mode:

```python
from core.isolation.base import ContainerRole

strategy = IsolationFactory.create(Path("."), method="docker")

# Container names follow pattern: auto-claude-{spec_name}-{role}
spec_name = "feature-auth"

# View logs
import subprocess
for role in ContainerRole:
    container = f"auto-claude-{spec_name}-{role.value}"
    result = subprocess.run(
        ["docker", "logs", container],
        capture_output=True,
        text=True
    )
    print(f"\n=== {role.value} logs ===")
    print(result.stdout)
```

---

## Best Practices

1. **Always call setup() first**
   ```python
   strategy = IsolationFactory.create(project_dir)
   strategy.setup()  # Initialize directories or build images
   ```

2. **Use get_or_create for idempotency**
   ```python
   # Safe to call multiple times
   env = strategy.get_or_create_environment("feature-x")
   ```

3. **Review changes before merging**
   ```python
   files = strategy.get_changed_files(spec_name)
   # Manual review or automated checks
   if all_checks_pass(files):
       strategy.merge_changes(spec_name, delete_after=True)
   ```

4. **Clean up failed builds**
   ```python
   if not success:
       strategy.remove_environment(spec_name, cleanup_branch=True)
   ```

5. **Use status callbacks for long-running builds**
   ```python
   await strategy.run_pipeline(
       spec_name,
       plan,
       on_status_change=lambda s, st, m: print(f"{s}: {st}")
   )
   ```

6. **Test Docker availability before using**
   ```python
   if not IsolationFactory.is_docker_available():
       # Fallback to worktree
       strategy = IsolationFactory.create(project_dir, method="worktree")
   ```

7. **Set appropriate resource limits for Docker**
   ```bash
   # For large builds
   export DOCKER_MEMORY_LIMIT=8g
   export DOCKER_CPU_SHARES=2048
   ```

---

## Summary

The isolation system provides a unified interface for safely building features in controlled environments:

- **IsolationFactory**: Creates the appropriate strategy based on settings
- **WorktreeIsolationStrategy**: Lightweight, local isolation (default)
- **DockerIsolationStrategy**: Full container isolation with multi-stage pipeline
- **Common Interface**: Switch between modes without changing code

Get started in 3 lines:
```python
strategy = IsolationFactory.create(Path("/workspace"))
strategy.setup()
await strategy.run_pipeline("my-feature", plan)
```

For questions or issues, see:
- API documentation: `core/isolation/base.py`
- Worktree implementation: `core/isolation/worktree_strategy.py`
- Docker implementation: `core/isolation/docker_strategy.py`
- Factory: `core/isolation/factory.py`
