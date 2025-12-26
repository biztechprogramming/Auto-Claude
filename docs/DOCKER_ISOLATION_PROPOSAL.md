# Docker Container Isolation Proposal (v2)

## Overview

This document outlines the architecture for Docker container-based isolation as an alternative to Git worktree-based isolation. The implementation uses a factory pattern to allow configuration-based selection of isolation strategy.

**Key Principle**: Either Docker mode OR Worktree mode, not both simultaneously.

---

## Architecture Summary

### Mode Selection

```bash
# In .env
ISOLATION_METHOD=worktree  # Default - uses existing code
ISOLATION_METHOD=docker    # Multi-container pipeline
```

### Worktree Mode (Existing)
- Uses `ClaudeSDKClient` with full security (sandbox, permissions, hooks)
- Configurable permissions via settings
- Single-process pipeline: planner → coder → qa_reviewer → qa_fixer
- Git worktrees for branch isolation

### Docker Mode (New)
- Orchestrator runs on host (planner, kanban, container lifecycle)
- Multi-container pipeline with feedback loops
- All containers use `ClaudeSDKClient`
- Work shared via git only (no shared volumes)
- Read-only database access; migrations via golang-migrate

---

## Docker Mode Architecture

### Container Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                     HOST / ORCHESTRATOR                               │
│  • Planner (creates implementation plan)                              │
│  • Kanban state management + comments                                 │
│  • Container lifecycle (create/destroy)                               │
│  • Routes feedback between containers                                 │
│  • Receives pass/fail results, updates task status                    │
└──────────────────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Developer   │───▶│  Evaluator   │───▶│     QA       │───▶ Human
│  Container   │◀───│  Container   │    │  Container   │     Review
│              │◀───────────────────────│              │
└──────────────┘    └──────────────┘    └──────────────┘
  git clone          git clone           git clone
  depth=1            feature branch      feature branch
  make changes       quality check       playwright tests
  git push           approve/reject      pass/fail
                    (with comments)     (with comments)
```

### Container Responsibilities

| Container | Purpose | Image | Lifecycle | Actions |
|-----------|---------|-------|-----------|---------|
| Developer | Implement code changes | `auto-claude-dev` | **Persistent** - Reused across iterations | First run: Clone (depth=1), create branch. Subsequent runs: Pull latest, implement feedback |
| Evaluator | Code quality review | `auto-claude-eval` | **One-shot** - Created per review | Clone feature branch, run quality prompts, approve or reject with comments |
| QA | Functional testing | `auto-claude-qa` | **One-shot** - Created per test run | Clone feature branch, run Playwright tests, pass or reject with comments |

### Feedback Loops

1. **Evaluator → Developer**: Quality issues found → comments added → **Developer container reused** to fix (fast iteration)
2. **QA → Developer**: Tests fail → comments added → **Developer container reused** to fix (fast iteration)
3. **All feedback** routes through orchestrator which updates kanban state

### Container Lifecycle & Cleanup

**Developer Container:**
- **Created once** per spec when first needed
- **Reused** across all feedback iterations (faster performance)
- **Cleaned up** automatically when:
  - Spec is approved and merged (`merge_changes()`)
  - Spec is discarded (`remove_environment(cleanup_branch=True)`)
  - Manual cleanup (`cleanup_containers()`)

**Evaluator/QA Containers:**
- **Created per run** as needed
- **Auto-removed** after completion (`docker run --rm`)
- No persistence required

**Example:**
```python
# Iteration 1: Developer container created
dev_result = run_developer(...)  # Creates persistent container

# Iteration 2: Developer container reused (fast!)
dev_result = run_developer(...)  # Reuses existing container

# After approval
strategy.merge_changes("feature-x")  # Cleans up all containers
```

### All Containers Include

- Claude SDK (`ClaudeSDKClient`)
- `CLAUDE_CODE_OAUTH_TOKEN` for authentication
- SQL query tools (MCP or native) - **read-only access**
- Git for work sharing
- golang-migrate for database migrations (https://github.com/golang-migrate/migrate)

---

## Container Images

### Image Hierarchy

```
auto-claude-base:latest
    │
    ├── auto-claude-dev:latest    (Developer)
    ├── auto-claude-eval:latest   (Evaluator)
    └── auto-claude-qa:latest     (QA - adds Playwright)
```

### Dockerfile.base

```dockerfile
# Base image for all Auto-Claude containers
# Contains: Claude SDK, SQL tools, git, common dependencies

FROM node:20-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    curl \
    postgresql-client \
    mysql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (includes SDK)
RUN npm install -g @anthropic-ai/claude-code

# Install Python for SDK usage
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Agent SDK
RUN pip3 install --break-system-packages claude-agent-sdk

# Install golang-migrate for database migrations
RUN curl -L https://github.com/golang-migrate/migrate/releases/download/v4.17.0/migrate.linux-amd64.tar.gz | tar xvz \
    && mv migrate /usr/local/bin/migrate

# Create workspace
RUN mkdir -p /workspace && chown node:node /workspace

# Set up git defaults
RUN git config --global user.email "auto-claude@local" && \
    git config --global user.name "Auto-Claude" && \
    git config --global init.defaultBranch main

WORKDIR /workspace

# Run as node user for security
USER node

# Default command (overridden by orchestrator)
CMD ["bash"]
```

### Dockerfile.developer

```dockerfile
# Developer container - implements code changes
FROM auto-claude-base:latest

# Developer-specific tools can be added here
# Initially same as base

LABEL container.role="developer"
```

### Dockerfile.evaluator

```dockerfile
# Evaluator container - code quality review
FROM auto-claude-base:latest

# Evaluator-specific tools can be added here
# Initially same as base, but configurable for different review approaches

LABEL container.role="evaluator"
```

### Dockerfile.qa

```dockerfile
# QA container - functional testing with Playwright
FROM auto-claude-base:latest

USER root

# Install Playwright dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libatspi2.0-0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright
RUN npm install -g playwright && \
    npx playwright install chromium firefox

# Install additional testing tools
RUN npm install -g \
    jest \
    vitest \
    cypress

USER node

LABEL container.role="qa"
```

---

## Files to Create

### 1. `apps/backend/core/isolation/__init__.py`

```python
"""
Isolation Strategy Module
=========================

Provides pluggable isolation strategies for running agent sessions.
Supports both Git worktree and Docker container isolation.
"""

from .base import IsolationStrategy, IsolationInfo, ContainerRole
from .factory import IsolationFactory
from .worktree_strategy import WorktreeIsolationStrategy
from .docker_strategy import DockerIsolationStrategy
from .orchestrator import DockerOrchestrator

__all__ = [
    "IsolationStrategy",
    "IsolationInfo",
    "ContainerRole",
    "IsolationFactory",
    "WorktreeIsolationStrategy",
    "DockerIsolationStrategy",
    "DockerOrchestrator",
]
```

### 2. `apps/backend/core/isolation/base.py`

```python
"""
Base classes for isolation strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ContainerRole(Enum):
    """Role of a container in the pipeline."""
    DEVELOPER = "developer"
    EVALUATOR = "evaluator"
    QA = "qa"


@dataclass
class FeedbackComment:
    """Feedback from evaluator or QA back to developer."""
    source: ContainerRole
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    severity: str = "error"  # error, warning, suggestion


@dataclass
class ContainerResult:
    """Result from a container execution."""
    role: ContainerRole
    success: bool
    exit_code: int
    output: str
    comments: list[FeedbackComment] = field(default_factory=list)
    commit_sha: Optional[str] = None  # For developer container


@dataclass
class IsolationInfo:
    """Information about an isolated execution environment."""
    spec_name: str
    working_dir: Path
    branch_name: str
    is_active: bool = True
    # Strategy-specific metadata
    container_id: Optional[str] = None  # Docker only
    container_role: Optional[ContainerRole] = None  # Docker only
    worktree_path: Optional[Path] = None  # Worktree only


class IsolationStrategy(ABC):
    """
    Abstract base class for isolation strategies.

    Both WorktreeIsolationStrategy and DockerIsolationStrategy
    implement this interface, allowing the runner to use either
    without knowing the implementation details.
    """

    def __init__(self, project_dir: Path, base_branch: Optional[str] = None):
        self.project_dir = project_dir
        self.base_branch = base_branch

    @abstractmethod
    def setup(self) -> None:
        """Initialize the isolation strategy (create directories, build images, etc.)."""
        pass

    @abstractmethod
    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create an isolated environment for a spec."""
        pass

    @abstractmethod
    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Get info about an existing environment, or None if it doesn't exist."""
        pass

    @abstractmethod
    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get existing environment or create a new one."""
        pass

    @abstractmethod
    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the full implementation pipeline.

        For worktree: planner → coder → qa_reviewer → qa_fixer
        For docker: developer → evaluator → qa (with feedback loops)

        Args:
            spec_name: The spec being implemented
            plan: The implementation plan
            on_status_change: Callback for kanban status updates

        Returns:
            True if pipeline completed successfully
        """
        pass

    @abstractmethod
    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Remove an isolated environment."""
        pass

    @abstractmethod
    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """Merge changes from the isolated environment back to base branch."""
        pass

    @abstractmethod
    def list_environments(self) -> list[IsolationInfo]:
        """List all active isolated environments."""
        pass

    @abstractmethod
    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get list of changed files (status, path) in the environment."""
        pass
```

### 3. `apps/backend/core/isolation/worktree_strategy.py`

```python
"""
Worktree-based isolation strategy.

This wraps the existing WorktreeManager and agent execution code,
maintaining full backward compatibility while conforming to the
IsolationStrategy interface.

Security: Uses ClaudeSDKClient with configurable permissions,
sandbox enabled, and bash_security_hook for command validation.
"""

import os
from pathlib import Path
from typing import Optional

from .base import IsolationStrategy, IsolationInfo
from core.worktree import WorktreeManager


class WorktreeIsolationStrategy(IsolationStrategy):
    """
    Isolation strategy using Git worktrees.

    Delegates to existing WorktreeManager for worktree operations
    and existing agent code for execution. This maintains the
    current security model:
    - Sandbox enabled (OS-level bash isolation)
    - File permissions restricted to project directory
    - Bash commands validated via bash_security_hook
    - Configurable permission overrides via settings
    """

    def __init__(
        self,
        project_dir: Path,
        base_branch: Optional[str] = None,
        permission_overrides: Optional[dict] = None,
    ):
        super().__init__(project_dir, base_branch)
        self._manager = WorktreeManager(project_dir, base_branch)
        self._permission_overrides = permission_overrides or {}

    def setup(self) -> None:
        """Initialize worktrees directory."""
        self._manager.setup()

    def get_permission_settings(self) -> dict:
        """
        Get permission settings for the SDK client.

        Merges default permissions with any configured overrides.
        """
        # Default permissions (from current client.py)
        default_permissions = {
            "sandbox": {"enabled": True, "autoAllowBashIfSandboxed": True},
            "permissions": {
                "defaultMode": "acceptEdits",
                "allow": [
                    "Read(./**)",
                    "Write(./**)",
                    "Edit(./**)",
                    "Glob(./**)",
                    "Grep(./**)",
                    "Bash(*)",
                ],
            },
        }

        # Apply overrides
        if self._permission_overrides:
            if "permissions" in self._permission_overrides:
                override_perms = self._permission_overrides["permissions"]
                if "allow" in override_perms:
                    # Extend or replace allow list
                    if override_perms.get("extend_allow", False):
                        default_permissions["permissions"]["allow"].extend(
                            override_perms["allow"]
                        )
                    else:
                        default_permissions["permissions"]["allow"] = override_perms["allow"]
                if "deny" in override_perms:
                    default_permissions["permissions"]["deny"] = override_perms["deny"]

            if "sandbox" in self._permission_overrides:
                default_permissions["sandbox"].update(self._permission_overrides["sandbox"])

        return default_permissions

    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create a worktree for the spec."""
        info = self._manager.create_worktree(spec_name)
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Get worktree info if it exists."""
        info = self._manager.get_worktree_info(spec_name)
        if info is None:
            return None
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get or create worktree."""
        info = self._manager.get_or_create_worktree(spec_name)
        return IsolationInfo(
            spec_name=spec_name,
            working_dir=info.path,
            branch_name=info.branch,
            is_active=info.is_active,
            worktree_path=info.path,
        )

    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the worktree-based pipeline.

        Uses existing agent code: planner → coder → qa_reviewer → qa_fixer
        """
        # Import here to avoid circular imports
        from agents import run_autonomous_agent

        env_info = self.get_or_create_environment(spec_name)

        # Run the existing autonomous agent pipeline
        # This handles the full planner → coder → qa_reviewer → qa_fixer flow
        success = await run_autonomous_agent(
            spec_dir=self.project_dir / ".auto-claude" / "specs" / spec_name,
            project_dir=env_info.working_dir,
            source_spec_dir=self.project_dir / ".auto-claude" / "specs" / spec_name,
        )

        if on_status_change:
            status = "completed" if success else "failed"
            on_status_change(spec_name, status)

        return success

    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Remove worktree."""
        self._manager.remove_worktree(spec_name, delete_branch=cleanup_branch)

    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """Merge worktree branch to base."""
        return self._manager.merge_worktree(spec_name, delete_after=delete_after)

    def list_environments(self) -> list[IsolationInfo]:
        """List all worktrees."""
        worktrees = self._manager.list_all_worktrees()
        return [
            IsolationInfo(
                spec_name=w.spec_name,
                working_dir=w.path,
                branch_name=w.branch,
                is_active=w.is_active,
                worktree_path=w.path,
            )
            for w in worktrees
        ]

    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get changed files in worktree."""
        return self._manager.get_changed_files(spec_name)
```

### 4. `apps/backend/core/isolation/docker_strategy.py`

```python
"""
Docker container-based isolation strategy.

Uses a multi-container pipeline:
1. Developer container - implements changes
2. Evaluator container - code quality review
3. QA container - functional testing

All containers use ClaudeSDKClient for Claude interactions.
Work is shared via git only (no shared volumes).
Database access is read-only; migrations use golang-migrate.
"""

import os
import subprocess
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .base import (
    IsolationStrategy,
    IsolationInfo,
    ContainerRole,
    ContainerResult,
    FeedbackComment,
)
from .orchestrator import DockerOrchestrator


class DockerIsolationStrategy(IsolationStrategy):
    """
    Isolation strategy using Docker containers.

    Pipeline:
    1. Orchestrator (host) creates implementation plan
    2. Developer container clones (depth=1), creates branch, implements, pushes
    3. Evaluator container clones feature branch, reviews quality
       - Approves → proceed to QA
       - Rejects → comments sent back, Developer container recreated
    4. QA container clones feature branch, runs Playwright tests
       - Passes → notify human for final review
       - Fails → comments sent back, Developer container recreated
    5. All state changes update kanban with comments
    """

    # Default image names
    DEFAULT_IMAGE_BASE = "auto-claude-base:latest"
    DEFAULT_IMAGE_DEVELOPER = "auto-claude-dev:latest"
    DEFAULT_IMAGE_EVALUATOR = "auto-claude-eval:latest"
    DEFAULT_IMAGE_QA = "auto-claude-qa:latest"

    # Resource limits
    DEFAULT_MEMORY = "4g"
    DEFAULT_CPU_SHARES = "1024"
    DEFAULT_PIDS_LIMIT = "256"

    def __init__(
        self,
        project_dir: Path,
        base_branch: Optional[str] = None,
        image_developer: Optional[str] = None,
        image_evaluator: Optional[str] = None,
        image_qa: Optional[str] = None,
        memory_limit: Optional[str] = None,
        cpu_shares: Optional[str] = None,
        repo_url: Optional[str] = None,
        database_url: Optional[str] = None,
        max_feedback_iterations: int = 3,
    ):
        super().__init__(project_dir, base_branch)

        # Container images (configurable)
        self.image_developer = image_developer or os.getenv(
            "DOCKER_IMAGE_DEVELOPER", self.DEFAULT_IMAGE_DEVELOPER
        )
        self.image_evaluator = image_evaluator or os.getenv(
            "DOCKER_IMAGE_EVALUATOR", self.DEFAULT_IMAGE_EVALUATOR
        )
        self.image_qa = image_qa or os.getenv(
            "DOCKER_IMAGE_QA", self.DEFAULT_IMAGE_QA
        )

        # Resource limits
        self.memory_limit = memory_limit or os.getenv(
            "DOCKER_MEMORY_LIMIT", self.DEFAULT_MEMORY
        )
        self.cpu_shares = cpu_shares or os.getenv(
            "DOCKER_CPU_SHARES", self.DEFAULT_CPU_SHARES
        )

        # Repository URL for cloning
        self.repo_url = repo_url or os.getenv("REPO_URL") or self._detect_repo_url()

        # Database (read-only)
        self.database_url = database_url or os.getenv("DATABASE_URL")

        # Feedback loop limit
        self.max_feedback_iterations = max_feedback_iterations

        # Orchestrator
        self._orchestrator = DockerOrchestrator(
            project_dir=project_dir,
            base_branch=base_branch or self._detect_base_branch(),
            repo_url=self.repo_url,
            images={
                ContainerRole.DEVELOPER: self.image_developer,
                ContainerRole.EVALUATOR: self.image_evaluator,
                ContainerRole.QA: self.image_qa,
            },
            memory_limit=self.memory_limit,
            cpu_shares=self.cpu_shares,
            database_url=self.database_url,
        )

    def _detect_repo_url(self) -> str:
        """Detect git remote URL."""
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        raise RuntimeError("Could not detect repository URL. Set REPO_URL env var.")

    def _detect_base_branch(self) -> str:
        """Detect the base branch (main/master)."""
        for branch in ["main", "master"]:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", branch],
                cwd=self.project_dir,
                capture_output=True,
            )
            if result.returncode == 0:
                return branch
        # Fallback to current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() or "main"

    def is_docker_available(self) -> bool:
        """Check if Docker is available."""
        try:
            subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def setup(self) -> None:
        """Ensure Docker is available and images are built."""
        if not self.is_docker_available():
            raise RuntimeError(
                "Docker is not available. Please install Docker or use worktree isolation."
            )

        # Build images if needed
        self._orchestrator.build_images()

    def create_environment(self, spec_name: str) -> IsolationInfo:
        """Create a branch for the spec (containers created on-demand)."""
        branch_name = f"auto-claude/{spec_name}"

        # Create branch on remote (via local git)
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=self.project_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", branch_name, self.base_branch or "main"],
            cwd=self.project_dir,
            capture_output=True,
            check=True,
        )

        return IsolationInfo(
            spec_name=spec_name,
            working_dir=self.project_dir,
            branch_name=branch_name,
            is_active=True,
        )

    def get_environment(self, spec_name: str) -> Optional[IsolationInfo]:
        """Check if environment (branch) exists."""
        branch_name = f"auto-claude/{spec_name}"
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            cwd=self.project_dir,
            capture_output=True,
        )
        if result.returncode != 0:
            return None

        return IsolationInfo(
            spec_name=spec_name,
            working_dir=self.project_dir,
            branch_name=branch_name,
            is_active=True,
        )

    def get_or_create_environment(self, spec_name: str) -> IsolationInfo:
        """Get or create environment."""
        existing = self.get_environment(spec_name)
        if existing:
            return existing
        return self.create_environment(spec_name)

    async def run_pipeline(
        self,
        spec_name: str,
        plan: dict,
        on_status_change: Optional[callable] = None,
    ) -> bool:
        """
        Run the Docker-based multi-container pipeline.

        Flow:
        1. Developer container implements the plan
        2. Evaluator container reviews quality
        3. If rejected, loop back to Developer with comments
        4. QA container runs tests
        5. If failed, loop back to Developer with comments
        6. If all pass, notify human
        """
        env_info = self.get_or_create_environment(spec_name)
        branch_name = env_info.branch_name

        accumulated_comments: list[FeedbackComment] = []
        iteration = 0

        while iteration < self.max_feedback_iterations:
            iteration += 1

            # Update status
            if on_status_change:
                on_status_change(spec_name, "in_progress", f"Iteration {iteration}")

            # 1. Developer container
            dev_result = await self._orchestrator.run_developer(
                spec_name=spec_name,
                branch_name=branch_name,
                plan=plan,
                feedback_comments=accumulated_comments,
            )

            if not dev_result.success:
                if on_status_change:
                    on_status_change(
                        spec_name, "failed",
                        f"Developer container failed: {dev_result.output[:200]}"
                    )
                return False

            # 2. Evaluator container
            eval_result = await self._orchestrator.run_evaluator(
                spec_name=spec_name,
                branch_name=branch_name,
                commit_sha=dev_result.commit_sha,
            )

            if not eval_result.success:
                # Rejected - collect comments and loop back
                accumulated_comments.extend(eval_result.comments)
                if on_status_change:
                    on_status_change(
                        spec_name, "needs_revision",
                        f"Evaluator rejected: {len(eval_result.comments)} comments"
                    )
                continue  # Loop back to developer

            # 3. QA container
            qa_result = await self._orchestrator.run_qa(
                spec_name=spec_name,
                branch_name=branch_name,
                commit_sha=dev_result.commit_sha,
            )

            if not qa_result.success:
                # Failed tests - collect comments and loop back
                accumulated_comments.extend(qa_result.comments)
                if on_status_change:
                    on_status_change(
                        spec_name, "needs_revision",
                        f"QA failed: {len(qa_result.comments)} issues"
                    )
                continue  # Loop back to developer

            # All passed!
            if on_status_change:
                on_status_change(spec_name, "ready_for_review", "All checks passed")
            return True

        # Max iterations reached
        if on_status_change:
            on_status_change(
                spec_name, "failed",
                f"Max iterations ({self.max_feedback_iterations}) reached"
            )
        return False

    def remove_environment(self, spec_name: str, cleanup_branch: bool = False) -> None:
        """Stop any running containers and optionally delete branch."""
        self._orchestrator.cleanup_containers(spec_name)

        if cleanup_branch:
            branch_name = f"auto-claude/{spec_name}"
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                cwd=self.project_dir,
                capture_output=True,
            )

    def merge_changes(self, spec_name: str, delete_after: bool = False) -> bool:
        """Merge spec branch to base branch."""
        branch_name = f"auto-claude/{spec_name}"
        base = self.base_branch or "main"

        # Checkout base branch
        result = subprocess.run(
            ["git", "checkout", base],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Failed to checkout base branch: {result.stderr}")
            return False

        # Merge spec branch
        result = subprocess.run(
            ["git", "merge", "--no-ff", branch_name, "-m", f"auto-claude: Merge {branch_name}"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Merge failed: {result.stderr}")
            subprocess.run(
                ["git", "merge", "--abort"],
                cwd=self.project_dir,
                capture_output=True,
            )
            return False

        if delete_after:
            self.remove_environment(spec_name, cleanup_branch=True)

        return True

    def list_environments(self) -> list[IsolationInfo]:
        """List all spec branches."""
        result = subprocess.run(
            ["git", "branch", "--list", "auto-claude/*"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

        environments = []
        for line in result.stdout.strip().split("\n"):
            branch = line.strip().lstrip("* ")
            if not branch:
                continue
            spec_name = branch.replace("auto-claude/", "")
            environments.append(
                IsolationInfo(
                    spec_name=spec_name,
                    working_dir=self.project_dir,
                    branch_name=branch,
                    is_active=True,
                )
            )

        return environments

    def get_changed_files(self, spec_name: str) -> list[tuple[str, str]]:
        """Get changed files between base and spec branch."""
        branch_name = f"auto-claude/{spec_name}"
        base = self.base_branch or "main"

        result = subprocess.run(
            ["git", "diff", "--name-status", f"{base}...{branch_name}"],
            cwd=self.project_dir,
            capture_output=True,
            text=True,
        )

        files = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                files.append((parts[0], parts[1]))
        return files
```

### 5. `apps/backend/core/isolation/orchestrator.py`

```python
"""
Docker Orchestrator

Manages container lifecycle and coordinates the multi-container pipeline.
Runs on the host, outside of Docker containers.
"""

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .base import ContainerRole, ContainerResult, FeedbackComment


@dataclass
class ContainerConfig:
    """Configuration for running a container."""
    image: str
    name: str
    role: ContainerRole
    env_vars: dict
    memory_limit: str
    cpu_shares: str


class DockerOrchestrator:
    """
    Orchestrates Docker containers for the isolation pipeline.

    Responsibilities:
    - Build container images
    - Create/destroy containers
    - Run containers with appropriate configuration
    - Collect results and feedback
    - Route feedback between containers
    """

    def __init__(
        self,
        project_dir: Path,
        base_branch: str,
        repo_url: str,
        images: dict[ContainerRole, str],
        memory_limit: str = "4g",
        cpu_shares: str = "1024",
        database_url: Optional[str] = None,
    ):
        self.project_dir = project_dir
        self.base_branch = base_branch
        self.repo_url = repo_url
        self.images = images
        self.memory_limit = memory_limit
        self.cpu_shares = cpu_shares
        self.database_url = database_url

    def _get_container_name(self, spec_name: str, role: ContainerRole) -> str:
        """Generate container name for a spec and role."""
        return f"auto-claude-{spec_name}-{role.value}"

    def _get_base_env_vars(self) -> dict:
        """Get base environment variables for all containers."""
        env = {
            "CLAUDE_CODE_OAUTH_TOKEN": os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", ""),
            "REPO_URL": self.repo_url,
        }

        # Read-only database access
        if self.database_url:
            env["DATABASE_URL"] = self.database_url
            env["DATABASE_READ_ONLY"] = "true"

        return env

    def build_images(self) -> None:
        """Build all required Docker images."""
        dockerfile_dir = Path(__file__).parent.parent.parent / "docker"

        # Build base image first
        base_dockerfile = dockerfile_dir / "Dockerfile.base"
        if base_dockerfile.exists():
            print("Building base image...")
            subprocess.run(
                [
                    "docker", "build",
                    "-f", str(base_dockerfile),
                    "-t", "auto-claude-base:latest",
                    str(dockerfile_dir),
                ],
                check=True,
            )

        # Build role-specific images
        for role, image in self.images.items():
            dockerfile = dockerfile_dir / f"Dockerfile.{role.value}"
            if dockerfile.exists():
                print(f"Building {role.value} image...")
                subprocess.run(
                    [
                        "docker", "build",
                        "-f", str(dockerfile),
                        "-t", image,
                        str(dockerfile_dir),
                    ],
                    check=True,
                )

    def cleanup_containers(self, spec_name: str) -> None:
        """Stop and remove all containers for a spec."""
        for role in ContainerRole:
            container_name = self._get_container_name(spec_name, role)
            subprocess.run(
                ["docker", "stop", container_name],
                capture_output=True,
            )
            subprocess.run(
                ["docker", "rm", container_name],
                capture_output=True,
            )

    async def run_developer(
        self,
        spec_name: str,
        branch_name: str,
        plan: dict,
        feedback_comments: list[FeedbackComment],
    ) -> ContainerResult:
        """
        Run the developer container.

        1. Clone repo with depth=1
        2. Create/checkout feature branch
        3. Implement the plan (addressing any feedback)
        4. Commit and push changes
        """
        container_name = self._get_container_name(spec_name, ContainerRole.DEVELOPER)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "BASE_BRANCH": self.base_branch,
            "IMPLEMENTATION_PLAN": json.dumps(plan),
        })

        # Include feedback if any
        if feedback_comments:
            env_vars["FEEDBACK_COMMENTS"] = json.dumps([
                {
                    "source": c.source.value,
                    "message": c.message,
                    "file_path": c.file_path,
                    "line_number": c.line_number,
                    "severity": c.severity,
                }
                for c in feedback_comments
            ])

        # Build docker run command
        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
        ]

        # Add environment variables
        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.DEVELOPER],
            "python", "/scripts/developer_agent.py",
        ])

        # Run container
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )

        # Parse output for commit SHA
        commit_sha = None
        for line in result.stdout.split("\n"):
            if line.startswith("COMMIT_SHA="):
                commit_sha = line.split("=", 1)[1].strip()
                break

        return ContainerResult(
            role=ContainerRole.DEVELOPER,
            success=result.returncode == 0,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            commit_sha=commit_sha,
        )

    async def run_evaluator(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the evaluator container.

        1. Clone the feature branch
        2. Run quality review prompts
        3. Return approval or rejection with comments
        """
        container_name = self._get_container_name(spec_name, ContainerRole.EVALUATOR)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "COMMIT_SHA": commit_sha or "",
        })

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
        ]

        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.EVALUATOR],
            "python", "/scripts/evaluator_agent.py",
        ])

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )

        # Parse output for approval/rejection and comments
        comments = []
        success = result.returncode == 0

        # Look for JSON feedback in output
        for line in result.stdout.split("\n"):
            if line.startswith("FEEDBACK_JSON="):
                try:
                    feedback = json.loads(line.split("=", 1)[1])
                    success = feedback.get("approved", False)
                    for c in feedback.get("comments", []):
                        comments.append(FeedbackComment(
                            source=ContainerRole.EVALUATOR,
                            message=c.get("message", ""),
                            file_path=c.get("file_path"),
                            line_number=c.get("line_number"),
                            severity=c.get("severity", "error"),
                        ))
                except json.JSONDecodeError:
                    pass
                break

        return ContainerResult(
            role=ContainerRole.EVALUATOR,
            success=success,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            comments=comments,
        )

    async def run_qa(
        self,
        spec_name: str,
        branch_name: str,
        commit_sha: Optional[str],
    ) -> ContainerResult:
        """
        Run the QA container.

        1. Clone the feature branch
        2. Run Playwright and other tests
        3. Return pass or failure with comments
        """
        container_name = self._get_container_name(spec_name, ContainerRole.QA)

        env_vars = self._get_base_env_vars()
        env_vars.update({
            "SPEC_NAME": spec_name,
            "BRANCH_NAME": branch_name,
            "COMMIT_SHA": commit_sha or "",
        })

        cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "--memory", self.memory_limit,
            "--cpu-shares", self.cpu_shares,
            "--pids-limit", "256",
            # QA container may need more resources for browser testing
            "--shm-size", "2g",
        ]

        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            self.images[ContainerRole.QA],
            "python", "/scripts/qa_agent.py",
        ])

        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )

        # Parse output for pass/fail and comments
        comments = []
        success = result.returncode == 0

        for line in result.stdout.split("\n"):
            if line.startswith("FEEDBACK_JSON="):
                try:
                    feedback = json.loads(line.split("=", 1)[1])
                    success = feedback.get("passed", False)
                    for c in feedback.get("comments", []):
                        comments.append(FeedbackComment(
                            source=ContainerRole.QA,
                            message=c.get("message", ""),
                            file_path=c.get("file_path"),
                            line_number=c.get("line_number"),
                            severity=c.get("severity", "error"),
                        ))
                except json.JSONDecodeError:
                    pass
                break

        return ContainerResult(
            role=ContainerRole.QA,
            success=success,
            exit_code=result.returncode,
            output=result.stdout + result.stderr,
            comments=comments,
        )
```

### 6. `apps/backend/core/isolation/factory.py`

```python
"""
Factory for creating isolation strategies based on settings.
"""

import os
from pathlib import Path
from typing import Optional

from .base import IsolationStrategy
from .worktree_strategy import WorktreeIsolationStrategy
from .docker_strategy import DockerIsolationStrategy


class IsolationFactory:
    """
    Factory for creating isolation strategies.

    Reads ISOLATION_METHOD from environment/settings and returns
    the appropriate strategy implementation.
    """

    WORKTREE = "worktree"
    DOCKER = "docker"

    @classmethod
    def create(
        cls,
        project_dir: Path,
        base_branch: Optional[str] = None,
        method: Optional[str] = None,
        **kwargs,
    ) -> IsolationStrategy:
        """
        Create an isolation strategy based on settings.

        Args:
            project_dir: The project directory to isolate
            base_branch: Base branch for branching (auto-detected if None)
            method: Override isolation method ("worktree" or "docker")
                    If None, reads from ISOLATION_METHOD env var
            **kwargs: Additional arguments passed to the strategy

        Returns:
            IsolationStrategy implementation
        """
        if method is None:
            method = os.getenv("ISOLATION_METHOD", cls.WORKTREE)

        method = method.lower().strip()

        if method == cls.DOCKER:
            return DockerIsolationStrategy(
                project_dir=project_dir,
                base_branch=base_branch,
                **kwargs,
            )
        elif method == cls.WORKTREE:
            return WorktreeIsolationStrategy(
                project_dir=project_dir,
                base_branch=base_branch,
                **kwargs,
            )
        else:
            raise ValueError(
                f"Unknown isolation method: {method}. "
                f"Use '{cls.WORKTREE}' or '{cls.DOCKER}'."
            )

    @classmethod
    def get_available_methods(cls) -> list[str]:
        """Return list of available isolation methods."""
        return [cls.WORKTREE, cls.DOCKER]

    @classmethod
    def is_docker_available(cls) -> bool:
        """Check if Docker isolation is available."""
        try:
            strategy = DockerIsolationStrategy(Path("."))
            return strategy.is_docker_available()
        except Exception:
            return False
```

---

## Configuration

### `.env` Settings

```bash
# =============================================================================
# ISOLATION METHOD
# =============================================================================
# Choose how Auto-Claude isolates code changes during builds.
#
# Options:
#   - worktree (default): Uses Git worktrees, runs locally with security hooks
#   - docker: Uses Docker containers for full OS-level isolation

ISOLATION_METHOD=worktree

# =============================================================================
# WORKTREE SETTINGS (only used if ISOLATION_METHOD=worktree)
# =============================================================================

# Permission overrides (JSON format, optional)
# Example: {"permissions": {"allow": ["Bash(npm *)"], "extend_allow": true}}
# WORKTREE_PERMISSION_OVERRIDES={}

# =============================================================================
# DOCKER SETTINGS (only used if ISOLATION_METHOD=docker)
# =============================================================================

# Container images (defaults shown)
# DOCKER_IMAGE_DEVELOPER=auto-claude-dev:latest
# DOCKER_IMAGE_EVALUATOR=auto-claude-eval:latest
# DOCKER_IMAGE_QA=auto-claude-qa:latest

# Resource limits
# DOCKER_MEMORY_LIMIT=4g
# DOCKER_CPU_SHARES=1024

# Repository URL (auto-detected from git remote if not set)
# REPO_URL=https://github.com/user/repo.git

# Database connection (read-only access for containers)
# DATABASE_URL=postgresql://user:pass@host:5432/db

# Maximum feedback iterations before failing
# MAX_FEEDBACK_ITERATIONS=3
```

---

## Key Differences: Worktree vs Docker

| Aspect | Worktree | Docker |
|--------|----------|--------|
| Isolation Level | Git-level | OS-level (container) |
| Execution | `ClaudeSDKClient` on host | `ClaudeSDKClient` in container |
| Security Model | Sandbox + permissions + hooks | Container isolation |
| Permissions | Configurable via settings | Container provides isolation |
| Auth | `CLAUDE_CODE_OAUTH_TOKEN` | `CLAUDE_CODE_OAUTH_TOKEN` |
| Pipeline | Single-process (existing agents) | Multi-container (dev → eval → qa) |
| Feedback Loops | qa_reviewer → qa_fixer | Evaluator → Dev, QA → Dev |
| Database | Direct access | Read-only, migrations via golang-migrate |
| Work Sharing | Worktree filesystem | Git only |
| Performance | Faster (no container overhead) | Container startup ~2-5s |
| Requirements | Git | Git + Docker |

---

## Implementation Order

### Phase 1: Core Module Structure
1. [ ] Create `core/isolation/` directory
2. [ ] Create `base.py` with abstract interface and data classes
3. [ ] Create `worktree_strategy.py` wrapping existing code
4. [ ] Create `factory.py` with settings-based creation
5. [ ] Create `__init__.py` with exports

### Phase 2: Docker Infrastructure
1. [ ] Create `docker/` directory for Dockerfiles
2. [ ] Create `Dockerfile.base` with Claude SDK + SQL tools
3. [ ] Create `Dockerfile.developer`, `Dockerfile.evaluator`, `Dockerfile.qa`
4. [ ] Test image builds

### Phase 3: Docker Strategy
1. [ ] Create `orchestrator.py` for container lifecycle
2. [ ] Create `docker_strategy.py` with multi-container pipeline
3. [ ] Create container agent scripts (`developer_agent.py`, etc.)
4. [ ] Test end-to-end pipeline

### Phase 4: Integration
1. [ ] Update `.env.example` with new settings
2. [ ] Update `run.py` to use IsolationFactory
3. [ ] Add kanban status callback integration
4. [ ] Test both strategies work correctly

### Phase 5: Documentation
1. [ ] Update CLAUDE.md with isolation options
2. [ ] Add troubleshooting for Docker issues
3. [ ] Document container agent scripts

---

## Next Steps

1. [ ] Review and approve this updated proposal
2. [ ] Create the `core/isolation/` module structure
3. [ ] Implement worktree strategy (wrap existing code)
4. [ ] Create Dockerfiles and test images
5. [ ] Implement orchestrator and docker strategy
6. [ ] Create container agent scripts
7. [ ] Integrate with existing run.py
8. [ ] Update documentation
