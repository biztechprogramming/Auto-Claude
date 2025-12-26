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
    repo_url: str
    base_branch: str = "main"
    branch_name: str
    spec_name: str
    task_description: str
    feedback_comments: Optional[str] = None


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
        logger.info(f"Repo: {request.repo_url}")
        logger.info(f"Branch: {request.branch_name}")

        server.status = TaskStatus.RUNNING
        server.current_task = request.dict()
        server.started_at = datetime.now()
        server.completed_at = None
        server.error = None

        # Run task in background
        asyncio.create_task(server._run_task(request))

        return {"message": "Task started", "status": server.status}
