"""
Base FastAPI server for Docker container agents.

Provides:
- Real-time log streaming
- Status endpoints
- Structured request/response
- Better error handling
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List
from collections import deque

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a task running in the container."""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class StartRequest(BaseModel):
    """Request to start a task."""
    task_description: str
    branch_name: str
    feedback_comments: Optional[str] = None


class CloneRequest(BaseModel):
    """Request to clone repository."""
    repo_url: str
    branch_name: str


class StatusResponse(BaseModel):
    """Current status of the container."""
    status: TaskStatus
    message: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class LogEntry(BaseModel):
    """A single log entry."""
    timestamp: datetime
    level: str
    message: str


class LogBuffer:
    """Thread-safe circular buffer for logs."""

    def __init__(self, maxlen: int = 1000):
        self.buffer = deque(maxlen=maxlen)
        self.subscribers: List[asyncio.Queue] = []

    def add(self, level: str, message: str):
        """Add a log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message
        )
        self.buffer.append(entry)

        # Notify all subscribers
        for queue in self.subscribers:
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                pass  # Drop log if queue is full

    def get_recent(self, count: int = 100) -> List[LogEntry]:
        """Get recent log entries."""
        return list(self.buffer)[-count:]

    async def subscribe(self) -> asyncio.Queue:
        """Subscribe to new log entries."""
        queue = asyncio.Queue(maxsize=100)
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from log entries."""
        if queue in self.subscribers:
            self.subscribers.remove(queue)


class BaseContainerServer:
    """Base server for container agents."""

    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.app = FastAPI(title=f"{name} Container API")
        self.logs = LogBuffer()

        # Task state
        self.status = TaskStatus.IDLE
        self.current_task: Optional[dict] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

        # Setup routes
        self._setup_routes()

        # Setup custom logging handler
        self._setup_logging()

    def _setup_logging(self):
        """Setup custom logging to capture logs in buffer."""
        class BufferHandler(logging.Handler):
            def __init__(self, log_buffer: LogBuffer):
                super().__init__()
                self.log_buffer = log_buffer

            def emit(self, record):
                try:
                    msg = self.format(record)
                    self.log_buffer.add(record.levelname, msg)
                except Exception:
                    self.handleError(record)

        handler = BufferHandler(self.logs)
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        logging.getLogger().addHandler(handler)

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/")
        async def root():
            return {"service": self.name, "status": "running"}

        @self.app.get("/health")
        async def health():
            return {"status": "healthy"}

        @self.app.get("/status")
        async def status() -> StatusResponse:
            """Get current status."""
            return StatusResponse(
                status=self.status,
                message=f"{self.name} is {self.status.value}",
                started_at=self.started_at,
                completed_at=self.completed_at,
                error=self.error
            )

        @self.app.get("/logs")
        async def get_logs(count: int = 100):
            """Get recent logs."""
            entries = self.logs.get_recent(count)
            return {"logs": [e.dict() for e in entries]}

        @self.app.post("/clone")
        async def clone_repository(request: CloneRequest):
            """Clone repository and checkout branch."""
            try:
                logger.info(f"Cloning repository: {request.repo_url}")
                logger.info(f"Branch: {request.branch_name}")

                # Get GitHub token
                gh_token = os.environ.get("GH_TOKEN")
                if not gh_token:
                    raise ValueError("GH_TOKEN environment variable not set")

                # Clean and setup workspace
                repo_dir = Path("/workspace")
                if repo_dir.exists():
                    logger.info("Cleaning existing workspace contents...")
                    # Don't delete /workspace itself, just clean its contents
                    for item in repo_dir.iterdir():
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                else:
                    repo_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Using workspace: {repo_dir}")

                # Authenticate GitHub
                await self._authenticate_github(gh_token)

                # Clone repository
                await self._clone_repository(request.repo_url, repo_dir)

                # Checkout branch
                await self._checkout_branch(repo_dir, request.branch_name)

                logger.info(f"✓ Repository cloned successfully to /workspace")
                return {"status": "success", "workspace": str(repo_dir)}

            except Exception as e:
                logger.error(f"Clone failed: {e}", exc_info=True)
                return {"status": "error", "error": str(e)}

        @self.app.websocket("/logs/stream")
        async def stream_logs(websocket: WebSocket):
            """Stream logs in real-time via WebSocket."""
            await websocket.accept()
            queue = await self.logs.subscribe()

            try:
                # Send recent logs first
                recent = self.logs.get_recent(50)
                for entry in recent:
                    await websocket.send_json(entry.dict())

                # Stream new logs
                while True:
                    entry = await queue.get()
                    await websocket.send_json(entry.dict())
            except WebSocketDisconnect:
                self.logs.unsubscribe(queue)
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                self.logs.unsubscribe(queue)

    async def _run_task(self, request: StartRequest):
        """Override this method in subclasses to implement task logic."""
        raise NotImplementedError("Subclass must implement _run_task")

    # ===== Git Operations (Common to All Containers) =====

    async def _setup_workspace(self, request: StartRequest, branch_name: str) -> Path:
        """
        Setup workspace: clean, clone repo, checkout branch.

        Args:
            request: The start request with repo info
            branch_name: The branch to checkout (can be different per container)

        Returns:
            Path to the workspace directory
        """
        repo_dir = Path("/workspace")

        # Clean workspace
        if repo_dir.exists():
            logger.info("Cleaning existing workspace...")
            shutil.rmtree(repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using workspace: {repo_dir}")

        # Authenticate GitHub
        gh_token = os.environ.get("GH_TOKEN")
        if not gh_token:
            raise ValueError("GH_TOKEN environment variable not set")
        await self._authenticate_github(gh_token)

        # Clone repository
        await self._clone_repository(request.repo_url, repo_dir)

        # Checkout branch
        await self._checkout_branch(repo_dir, branch_name)

        return repo_dir

    async def _authenticate_github(self, token: str):
        """Authenticate GitHub CLI."""
        logger.info("Authenticating with GitHub...")

        try:
            process = await asyncio.create_subprocess_exec(
                "gh", "auth", "setup-git",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if stdout:
                logger.info(f"gh output: {stdout.decode().strip()}")
            if stderr:
                logger.info(f"gh info: {stderr.decode().strip()}")

            logger.info("Git credentials configured (using GH_TOKEN)")

        except Exception as e:
            logger.error(f"GitHub authentication error: {e}")
            raise

    async def _clone_repository(self, repo_url: str, repo_dir: Path):
        """Clone the repository."""
        logger.info(f"Cloning repository: {repo_url}")

        process = await asyncio.create_subprocess_exec(
            "git", "clone", repo_url, str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Clone failed: {stderr.decode()}")
            raise RuntimeError(f"Repository clone failed: {stderr.decode()}")

        logger.info("Repository cloned successfully")

    async def _checkout_branch(self, repo_dir: Path, branch_name: str):
        """
        Checkout a branch (create if doesn't exist).

        For developer: creates new feature branch
        For evaluator/QA: checks out existing feature branch
        """
        logger.info(f"Checking out branch: {branch_name}")

        # Try to checkout existing branch first
        process = await asyncio.create_subprocess_exec(
            "git", "checkout", branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0:
            logger.info(f"Checked out existing branch: {branch_name}")
            return

        # Branch doesn't exist, create it
        logger.info(f"Branch doesn't exist, creating: {branch_name}")
        process = await asyncio.create_subprocess_exec(
            "git", "checkout", "-b", branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Branch creation failed: {stderr.decode()}")
            raise RuntimeError(f"Branch creation failed: {stderr.decode()}")

        logger.info(f"Branch {branch_name} created and checked out")

    async def _commit_changes(self, repo_dir: Path, message: str):
        """Commit changes."""
        logger.info("Committing changes...")

        # Add all changes
        process = await asyncio.create_subprocess_exec(
            "git", "add", ".",
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # Commit
        process = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", message,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            # Check if there are no changes to commit
            if "nothing to commit" in stderr.decode():
                logger.info("No changes to commit")
                return
            logger.error(f"Commit failed: {stderr.decode()}")
            raise RuntimeError(f"Commit failed: {stderr.decode()}")

        logger.info("Changes committed")

    async def _push_changes(self, repo_dir: Path, branch_name: str):
        """Push changes to remote."""
        logger.info(f"Pushing to remote branch: {branch_name}")

        process = await asyncio.create_subprocess_exec(
            "git", "push", "-u", "origin", branch_name,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Push failed: {stderr.decode()}")
            raise RuntimeError(f"Push failed: {stderr.decode()}")

        logger.info("Changes pushed to GitHub successfully!")

    def run(self):
        """Start the FastAPI server."""
        logger.info(f"Starting {self.name} server on port {self.port}")
        uvicorn.run(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="info"
        )


def create_start_endpoint(server: BaseContainerServer):
    """Create a /start endpoint for a server."""

    @server.app.post("/start")
    async def start_task(request: StartRequest):
        """Start a new task."""
        if server.status == TaskStatus.RUNNING:
            raise HTTPException(status_code=409, detail="Task already running")

        logger.info(f"Starting task: {request.task_description}")
        logger.info(f"Branch: {request.branch_name}")

        server.status = TaskStatus.RUNNING
        server.current_task = request.dict()
        server.started_at = datetime.now()
        server.completed_at = None
        server.error = None

        # Run task in background
        asyncio.create_task(server._run_task(request))

        return {"message": "Task started", "status": server.status}
