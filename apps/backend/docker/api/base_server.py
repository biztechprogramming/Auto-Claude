"""
Base Container Server Module
=============================

Provides the base FastAPI server class for Docker containers.
All container-specific servers extend this base class.
"""

import os
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Status of a container task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StartRequest(BaseModel):
    """Request model for starting a container task."""

    spec_id: str
    spec_content: str
    branch_name: str
    workspace_path: str = "/workspace"
    project_context: Optional[str] = None
    memory_content: Optional[str] = None
    feedback_comments: Optional[list[str]] = None
    database_context: Optional[str] = None  # Context from database analysis step


class StartResponse(BaseModel):
    """Response model for task start."""

    status: TaskStatus
    message: str
    task_id: Optional[str] = None


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str
    name: str
    version: str = "1.0.0"


class StatusResponse(BaseModel):
    """Response model for task status."""

    status: TaskStatus
    message: str
    progress: int = 0
    current_step: Optional[str] = None


@dataclass
class ContainerContext:
    """Context for the current container task."""

    spec_id: str
    spec_content: str
    branch_name: str
    workspace_path: Path
    project_context: str = ""
    memory_content: str = ""
    feedback_comments: list[str] = field(default_factory=list)
    database_context: str = ""

    @classmethod
    def from_request(cls, request: StartRequest) -> "ContainerContext":
        """Create a ContainerContext from a StartRequest."""
        return cls(
            spec_id=request.spec_id,
            spec_content=request.spec_content,
            branch_name=request.branch_name,
            workspace_path=Path(request.workspace_path),
            project_context=request.project_context or "",
            memory_content=request.memory_content or "",
            feedback_comments=request.feedback_comments or [],
            database_context=request.database_context or "",
        )


class BaseContainerServer(ABC):
    """
    Base class for Docker container API servers.

    Provides common functionality for:
    - Health check endpoint
    - Task status tracking
    - Prompt loading and formatting
    - Error handling

    Subclasses must implement:
    - _run_task: Execute the container's main task
    """

    def __init__(self, name: str, port: Optional[int] = None):
        """
        Initialize the container server.

        Args:
            name: Human-readable name for the container
            port: Port to listen on (default: from PORT env var or 8000)
        """
        self.name = name
        self.port = port or int(os.environ.get("PORT", 8000))
        self.app = FastAPI(
            title=f"{name} Container",
            description=f"API server for the {name} container in the autonomous build pipeline",
            version="1.0.0",
        )
        self._task_status = TaskStatus.PENDING
        self._task_message = "Ready to accept tasks"
        self._task_progress = 0
        self._current_step: Optional[str] = None
        self._context: Optional[ContainerContext] = None

        # Register common endpoints
        self._register_health_endpoint()
        self._register_status_endpoint()

    def _register_health_endpoint(self) -> None:
        """Register the /health endpoint."""

        @self.app.get("/health", response_model=HealthResponse)
        async def health() -> HealthResponse:
            return HealthResponse(
                status="healthy",
                name=self.name,
            )

    def _register_status_endpoint(self) -> None:
        """Register the /status endpoint."""

        @self.app.get("/status", response_model=StatusResponse)
        async def status() -> StatusResponse:
            return StatusResponse(
                status=self._task_status,
                message=self._task_message,
                progress=self._task_progress,
                current_step=self._current_step,
            )

    def update_status(
        self,
        status: TaskStatus,
        message: str,
        progress: int = 0,
        current_step: Optional[str] = None,
    ) -> None:
        """
        Update the current task status.

        Args:
            status: New task status
            message: Status message
            progress: Progress percentage (0-100)
            current_step: Current step being executed
        """
        self._task_status = status
        self._task_message = message
        self._task_progress = progress
        self._current_step = current_step
        logger.info(f"[{self.name}] Status: {status.value} - {message}")

    @abstractmethod
    async def _run_task(self, request: StartRequest) -> None:
        """
        Execute the container's main task.

        This method must be implemented by subclasses to define
        the container-specific logic.

        Args:
            request: The task start request
        """
        pass

    def load_prompt(self, prompt_file: str) -> str:
        """
        Load a prompt template from the prompts directory.

        Args:
            prompt_file: Path to the prompt file (relative to prompts/)

        Returns:
            The prompt template content
        """
        # Try multiple locations for the prompt file
        locations = [
            Path("/workspace/apps/backend/prompts") / prompt_file,
            Path("/app/prompts") / prompt_file,
            Path("prompts") / prompt_file,
        ]

        for path in locations:
            if path.exists():
                return path.read_text()

        raise FileNotFoundError(f"Prompt file not found: {prompt_file}")

    def format_prompt(self, template: str, **kwargs) -> str:
        """
        Format a prompt template with the given variables.

        Uses safe formatting that ignores missing placeholders.

        Args:
            template: The prompt template
            **kwargs: Variables to substitute

        Returns:
            The formatted prompt
        """
        return safe_format_prompt(template, **kwargs)

    def run(self) -> None:
        """Start the FastAPI server."""
        import uvicorn

        logger.info(f"Starting {self.name} container on port {self.port}")
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)


def create_start_endpoint(server: BaseContainerServer) -> None:
    """
    Create the /start endpoint for a container server.

    This is a factory function that creates the endpoint and
    wires it to the server's _run_task method.

    Args:
        server: The container server instance
    """

    @server.app.post("/start", response_model=StartResponse)
    async def start(request: StartRequest) -> StartResponse:
        # Check if already running
        if server._task_status == TaskStatus.RUNNING:
            raise HTTPException(
                status_code=409,
                detail="Task already running",
            )

        try:
            # Update status to running
            server.update_status(
                TaskStatus.RUNNING,
                "Starting task execution",
            )

            # Store context
            server._context = ContainerContext.from_request(request)

            # Execute the task
            await server._run_task(request)

            # Update status to completed
            server.update_status(
                TaskStatus.COMPLETED,
                "Task completed successfully",
                progress=100,
            )

            return StartResponse(
                status=TaskStatus.COMPLETED,
                message="Task completed successfully",
                task_id=request.spec_id,
            )

        except Exception as e:
            logger.error(f"Task failed: {e}", exc_info=True)
            server.update_status(
                TaskStatus.FAILED,
                f"Task failed: {str(e)}",
            )
            raise HTTPException(
                status_code=500,
                detail=str(e),
            )


def safe_format_prompt(template: str, **kwargs) -> str:
    """
    Safely format a prompt template, ignoring missing placeholders.

    This function handles cases where the template contains
    placeholders that are not provided in kwargs.

    Args:
        template: The prompt template
        **kwargs: Variables to substitute

    Returns:
        The formatted prompt
    """
    import re

    def replace_placeholder(match: re.Match) -> str:
        key = match.group(1)
        return str(kwargs.get(key, match.group(0)))

    # Match {placeholder} patterns
    pattern = r"\{(\w+)\}"
    return re.sub(pattern, replace_placeholder, template)
