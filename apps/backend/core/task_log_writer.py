"""
Task Log Writer - Observer Pattern

Observes Docker container logs and writes structured task_logs.json
for the UI to consume in real-time.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

TaskLogPhase = Literal["planning", "coding", "validation", "testing"]
TaskPhaseStatus = Literal["pending", "active", "completed", "failed"]
WorkflowStatus = Literal["planning", "coding", "ai_review", "ai_testing", "needs_revision", "ready_for_review", "failed"]


class TaskLogWriter:
    """
    Writes structured task logs that the UI can watch and display.

    Implements Observer pattern - observes container output and updates logs.
    """

    def __init__(self, spec_dir: Path):
        self.spec_dir = spec_dir
        self.log_file = spec_dir / "task_logs.json"
        self._ensure_initialized()

    def _ensure_initialized(self):
        """Initialize task_logs.json if it doesn't exist."""
        if not self.log_file.exists():
            initial_logs = {
                "spec_id": self.spec_dir.name,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "workflow_status": "planning",
                "current_step": None,
                "iteration": 0,
                "phases": {
                    "planning": {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "entries": []
                    },
                    "coding": {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "entries": []
                    },
                    "validation": {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "entries": []
                    },
                    "testing": {
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "entries": []
                    }
                }
            }
            self._write_logs(initial_logs)

    def _read_logs(self) -> dict:
        """Read current logs from file."""
        if self.log_file.exists():
            try:
                return json.loads(self.log_file.read_text())
            except json.JSONDecodeError:
                # File corrupted, reinitialize
                pass

        # Return default structure
        return {
            "spec_id": self.spec_dir.name,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "workflow_status": "planning",
            "current_step": None,
            "iteration": 0,
            "phases": {
                "planning": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "entries": []
                },
                "coding": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "entries": []
                },
                "validation": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "entries": []
                },
                "testing": {
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "entries": []
                }
            }
        }

    def _write_logs(self, logs: dict):
        """Write logs to file atomically with Windows file lock retry."""
        import time

        logs["updated_at"] = datetime.now().isoformat()

        # Atomic write: write to temp file, then rename
        # Retry on Windows file lock errors
        temp_file = self.log_file.with_suffix(".tmp")

        for attempt in range(3):
            try:
                temp_file.write_text(json.dumps(logs, indent=2))
                temp_file.replace(self.log_file)
                return
            except (OSError, PermissionError) as e:
                if attempt < 2:
                    time.sleep(0.1)  # 100ms delay before retry
                else:
                    # Last attempt failed, raise the error
                    raise

    def set_phase_status(self, phase: TaskLogPhase, status: TaskPhaseStatus):
        """Update phase status (pending -> active -> completed/failed)."""
        logs = self._read_logs()
        logs["phases"][phase]["status"] = status

        # Update timestamps based on status
        now = datetime.now().isoformat()
        if status == "active" and logs["phases"][phase]["started_at"] is None:
            logs["phases"][phase]["started_at"] = now
        elif status in ("completed", "failed"):
            logs["phases"][phase]["completed_at"] = now

        self._write_logs(logs)

    def add_log_entry(
        self,
        phase: TaskLogPhase,
        content: str,
        entry_type: str = "text",
        detail: Optional[str] = None
    ):
        """Add a log entry to a phase."""
        logs = self._read_logs()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content
        }

        if detail:
            entry["detail"] = detail

        logs["phases"][phase]["entries"].append(entry)
        self._write_logs(logs)

    def observe_container_log(self, phase: TaskLogPhase, log_line: str):
        """
        Observe a container log line and extract relevant info.

        Parses Docker container output and creates structured log entries.
        """
        # Skip empty lines
        if not log_line.strip():
            return

        # Parse INFO/ERROR log lines
        info_match = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[INFO\] (.+)$", log_line)
        if info_match:
            self.add_log_entry(phase, info_match.group(1), "info")
            return

        error_match = re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[ERROR\] (.+)$", log_line)
        if error_match:
            self.add_log_entry(phase, error_match.group(1), "error")
            return

        # Parse uvicorn/fastapi logs (filter out noise)
        if "uvicorn" in log_line.lower() or "INFO:" in log_line:
            # Skip server startup logs
            if any(x in log_line for x in ["Started server", "Uvicorn running", "Application startup"]):
                return

            # HTTP requests are useful
            if " HTTP/" in log_line:
                # Parse HTTP request: "GET /health HTTP/1.1" 200 OK
                http_match = re.search(r'"([A-Z]+) (/[^\s"]*)[^"]*" (\d+)', log_line)
                if http_match:
                    method, path, status = http_match.groups()
                    self.add_log_entry(phase, f"{method} {path} → {status}", "info")
                return

        # Default: add as text entry (last 200 chars to avoid huge entries)
        if len(log_line) > 200:
            self.add_log_entry(phase, log_line[:200] + "...", "text", detail=log_line)
        else:
            self.add_log_entry(phase, log_line, "text")

    def mark_phase_complete(self, phase: TaskLogPhase, success: bool = True):
        """Mark a phase as completed or failed."""
        status: TaskPhaseStatus = "completed" if success else "failed"
        self.set_phase_status(phase, status)

        message = "✓ Phase completed successfully" if success else "✗ Phase failed"
        entry_type = "success" if success else "error"
        self.add_log_entry(phase, message, entry_type)

    # Workflow-level state management methods

    def set_workflow_status(self, status: WorkflowStatus):
        """Update the overall workflow status."""
        logs = self._read_logs()
        logs["workflow_status"] = status
        self._write_logs(logs)

    def set_current_step(self, step_name: Optional[str]):
        """Update the current step being executed."""
        logs = self._read_logs()
        logs["current_step"] = step_name
        self._write_logs(logs)

    def set_iteration(self, iteration: int):
        """Update the current iteration counter."""
        logs = self._read_logs()
        logs["iteration"] = iteration
        self._write_logs(logs)

    def get_workflow_status(self) -> WorkflowStatus:
        """Get the current workflow status."""
        logs = self._read_logs()
        return logs.get("workflow_status", "planning")

    def get_iteration(self) -> int:
        """Get the current iteration counter."""
        logs = self._read_logs()
        return logs.get("iteration", 0)

    def is_phase_complete(self, phase: TaskLogPhase) -> bool:
        """Check if a phase is marked as completed."""
        logs = self._read_logs()
        return logs.get("phases", {}).get(phase, {}).get("status") == "completed"

    def reset_phase(self, phase: TaskLogPhase):
        """Reset a phase to pending state (for manual retry)."""
        logs = self._read_logs()
        logs["phases"][phase] = {
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "entries": []
        }
        self._write_logs(logs)

    def update_workflow_state(self, workflow_status: WorkflowStatus, current_step: Optional[str] = None, iteration: Optional[int] = None):
        """
        Update multiple workflow state fields atomically.

        Args:
            workflow_status: Overall workflow status
            current_step: Current step name (optional)
            iteration: Current iteration (optional)
        """
        logs = self._read_logs()
        logs["workflow_status"] = workflow_status

        if current_step is not None:
            logs["current_step"] = current_step

        if iteration is not None:
            logs["iteration"] = iteration

        self._write_logs(logs)
