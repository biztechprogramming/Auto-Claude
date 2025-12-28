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

TaskLogPhase = Literal["planning", "coding", "validation"]
TaskPhaseStatus = Literal["pending", "active", "completed", "failed"]


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
                "phases": {
                    "planning": {"status": "pending", "entries": []},
                    "coding": {"status": "pending", "entries": []},
                    "validation": {"status": "pending", "entries": []}
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
            "phases": {
                "planning": {"status": "pending", "entries": []},
                "coding": {"status": "pending", "entries": []},
                "validation": {"status": "pending", "entries": []}
            }
        }

    def _write_logs(self, logs: dict):
        """Write logs to file atomically."""
        logs["updated_at"] = datetime.now().isoformat()

        # Atomic write: write to temp file, then rename
        temp_file = self.log_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(logs, indent=2))
        temp_file.replace(self.log_file)

    def set_phase_status(self, phase: TaskLogPhase, status: TaskPhaseStatus):
        """Update phase status (pending -> active -> completed/failed)."""
        logs = self._read_logs()
        logs["phases"][phase]["status"] = status
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
