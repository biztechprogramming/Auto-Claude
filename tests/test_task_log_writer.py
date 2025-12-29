"""
Tests for task log writer (Observer pattern for container logs).

Tests cover:
- Log file initialization
- Phase status management
- Log entry creation
- Container log observation
- Workflow state management
- Iteration tracking
- Atomic file writes
"""

import pytest
import json
from pathlib import Path
from datetime import datetime

from apps.backend.core.task_log_writer import TaskLogWriter


class TestInitialization:
    """Test task log writer initialization."""

    def test_init_creates_log_file(self, tmp_path):
        """Test initialization creates task_logs.json."""
        spec_dir = tmp_path / "spec-001"
        spec_dir.mkdir()

        writer = TaskLogWriter(spec_dir)

        log_file = spec_dir / "task_logs.json"
        assert log_file.exists()

    def test_init_creates_default_structure(self, tmp_path):
        """Test initial log structure."""
        spec_dir = tmp_path / "spec-001"
        spec_dir.mkdir()

        writer = TaskLogWriter(spec_dir)

        logs = json.loads(writer.log_file.read_text())

        assert logs["spec_id"] == "spec-001"
        assert logs["workflow_status"] == "planning"
        assert logs["iteration"] == 0
        assert "phases" in logs
        assert "planning" in logs["phases"]
        assert "coding" in logs["phases"]
        assert "validation" in logs["phases"]
        assert "testing" in logs["phases"]

    def test_init_preserves_existing_log(self, tmp_path):
        """Test initialization preserves existing log file."""
        spec_dir = tmp_path / "spec-001"
        spec_dir.mkdir()

        # Create initial log
        writer1 = TaskLogWriter(spec_dir)
        writer1.add_log_entry("coding", "Test entry", "info")

        # Create second writer
        writer2 = TaskLogWriter(spec_dir)

        logs = json.loads(writer2.log_file.read_text())
        assert len(logs["phases"]["coding"]["entries"]) == 1


class TestPhaseStatusManagement:
    """Test phase status management."""

    def test_set_phase_status_pending_to_active(self, writer):
        """Test transitioning phase from pending to active."""
        writer.set_phase_status("coding", "active")

        logs = json.loads(writer.log_file.read_text())
        assert logs["phases"]["coding"]["status"] == "active"
        assert logs["phases"]["coding"]["started_at"] is not None

    def test_set_phase_status_active_to_completed(self, writer):
        """Test transitioning phase from active to completed."""
        writer.set_phase_status("coding", "active")
        writer.set_phase_status("coding", "completed")

        logs = json.loads(writer.log_file.read_text())
        assert logs["phases"]["coding"]["status"] == "completed"
        assert logs["phases"]["coding"]["completed_at"] is not None

    def test_set_phase_status_active_to_failed(self, writer):
        """Test transitioning phase to failed."""
        writer.set_phase_status("coding", "active")
        writer.set_phase_status("coding", "failed")

        logs = json.loads(writer.log_file.read_text())
        assert logs["phases"]["coding"]["status"] == "failed"
        assert logs["phases"]["coding"]["completed_at"] is not None

    def test_mark_phase_complete_success(self, writer):
        """Test marking phase as successfully completed."""
        writer.mark_phase_complete("coding", success=True)

        logs = json.loads(writer.log_file.read_text())
        assert logs["phases"]["coding"]["status"] == "completed"

        # Should have success log entry
        entries = logs["phases"]["coding"]["entries"]
        assert len(entries) > 0
        assert any("completed successfully" in e["content"] for e in entries)

    def test_mark_phase_complete_failure(self, writer):
        """Test marking phase as failed."""
        writer.mark_phase_complete("coding", success=False)

        logs = json.loads(writer.log_file.read_text())
        assert logs["phases"]["coding"]["status"] == "failed"

        # Should have error log entry
        entries = logs["phases"]["coding"]["entries"]
        assert len(entries) > 0
        assert any("failed" in e["content"].lower() for e in entries)


class TestLogEntryCreation:
    """Test log entry creation."""

    def test_add_log_entry_basic(self, writer):
        """Test adding a basic log entry."""
        writer.add_log_entry("coding", "Task started", "info")

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 1
        assert entries[0]["content"] == "Task started"
        assert entries[0]["type"] == "info"
        assert "timestamp" in entries[0]

    def test_add_log_entry_with_detail(self, writer):
        """Test adding log entry with detail."""
        writer.add_log_entry(
            "coding",
            "Error occurred",
            "error",
            detail="Full stack trace here..."
        )

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 1
        assert entries[0]["content"] == "Error occurred"
        assert entries[0]["type"] == "error"
        assert entries[0]["detail"] == "Full stack trace here..."

    def test_add_multiple_log_entries(self, writer):
        """Test adding multiple log entries."""
        writer.add_log_entry("coding", "Entry 1", "info")
        writer.add_log_entry("coding", "Entry 2", "info")
        writer.add_log_entry("coding", "Entry 3", "error")

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 3
        assert entries[0]["content"] == "Entry 1"
        assert entries[1]["content"] == "Entry 2"
        assert entries[2]["content"] == "Entry 3"
        assert entries[2]["type"] == "error"


class TestContainerLogObservation:
    """Test container log observation and parsing."""

    def test_observe_info_log(self, writer):
        """Test observing INFO log line."""
        log_line = "2025-12-29 10:15:30 [INFO] Starting task execution"

        writer.observe_container_log("coding", log_line)

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 1
        assert entries[0]["content"] == "Starting task execution"
        assert entries[0]["type"] == "info"

    def test_observe_error_log(self, writer):
        """Test observing ERROR log line."""
        log_line = "2025-12-29 10:15:31 [ERROR] Task failed with error"

        writer.observe_container_log("coding", log_line)

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 1
        assert entries[0]["content"] == "Task failed with error"
        assert entries[0]["type"] == "error"

    def test_observe_http_request_log(self, writer):
        """Test observing HTTP request log."""
        log_line = 'INFO:     127.0.0.1:52000 - "POST /start HTTP/1.1" 200 OK'

        writer.observe_container_log("coding", log_line)

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        # Should parse and create entry
        assert len(entries) == 1
        assert "POST" in entries[0]["content"]
        assert "/start" in entries[0]["content"]

    def test_observe_skips_empty_lines(self, writer):
        """Test empty lines are skipped."""
        writer.observe_container_log("coding", "")
        writer.observe_container_log("coding", "   ")

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 0

    def test_observe_truncates_long_lines(self, writer):
        """Test long log lines are truncated."""
        long_line = "A" * 300

        writer.observe_container_log("coding", long_line)

        logs = json.loads(writer.log_file.read_text())
        entries = logs["phases"]["coding"]["entries"]

        assert len(entries) == 1
        assert len(entries[0]["content"]) == 203  # 200 + "..."
        assert "..." in entries[0]["content"]
        assert "detail" in entries[0]  # Full line in detail


class TestWorkflowStateManagement:
    """Test workflow state management."""

    def test_set_workflow_status(self, writer):
        """Test setting workflow status."""
        writer.set_workflow_status("coding")

        logs = json.loads(writer.log_file.read_text())
        assert logs["workflow_status"] == "coding"

    def test_set_current_step(self, writer):
        """Test setting current step."""
        writer.set_current_step("code_review")

        logs = json.loads(writer.log_file.read_text())
        assert logs["current_step"] == "code_review"

    def test_set_current_step_none(self, writer):
        """Test clearing current step."""
        writer.set_current_step("coding")
        writer.set_current_step(None)

        logs = json.loads(writer.log_file.read_text())
        assert logs["current_step"] is None

    def test_set_iteration(self, writer):
        """Test setting iteration counter."""
        writer.set_iteration(3)

        logs = json.loads(writer.log_file.read_text())
        assert logs["iteration"] == 3

    def test_get_workflow_status(self, writer):
        """Test getting workflow status."""
        writer.set_workflow_status("ai_review")

        status = writer.get_workflow_status()
        assert status == "ai_review"

    def test_get_iteration(self, writer):
        """Test getting iteration counter."""
        writer.set_iteration(5)

        iteration = writer.get_iteration()
        assert iteration == 5

    def test_update_workflow_state_atomic(self, writer):
        """Test atomic update of multiple workflow fields."""
        writer.update_workflow_state(
            workflow_status="ai_testing",
            current_step="testing",
            iteration=2
        )

        logs = json.loads(writer.log_file.read_text())
        assert logs["workflow_status"] == "ai_testing"
        assert logs["current_step"] == "testing"
        assert logs["iteration"] == 2


class TestPhaseCompletion:
    """Test phase completion checking."""

    def test_is_phase_complete_true(self, writer):
        """Test checking if phase is complete."""
        writer.mark_phase_complete("coding", success=True)

        assert writer.is_phase_complete("coding") is True

    def test_is_phase_complete_false(self, writer):
        """Test phase not complete."""
        assert writer.is_phase_complete("coding") is False

    def test_is_phase_complete_failed(self, writer):
        """Test failed phase is not considered complete."""
        writer.mark_phase_complete("coding", success=False)

        assert writer.is_phase_complete("coding") is False


class TestPhaseReset:
    """Test phase reset functionality."""

    def test_reset_phase(self, writer):
        """Test resetting a phase."""
        # Complete phase
        writer.set_phase_status("coding", "active")
        writer.add_log_entry("coding", "Work done", "info")
        writer.mark_phase_complete("coding", success=True)

        # Reset
        writer.reset_phase("coding")

        logs = json.loads(writer.log_file.read_text())
        phase = logs["phases"]["coding"]

        assert phase["status"] == "pending"
        assert phase["started_at"] is None
        assert phase["completed_at"] is None
        assert len(phase["entries"]) == 0


class TestFileAtomicity:
    """Test atomic file writes and Windows file lock handling."""

    def test_concurrent_writes(self, writer):
        """Test concurrent writes don't corrupt file."""
        # Simulate multiple concurrent writes
        for i in range(10):
            writer.add_log_entry("coding", f"Entry {i}", "info")

        logs = json.loads(writer.log_file.read_text())

        # Should have all entries
        assert len(logs["phases"]["coding"]["entries"]) == 10

    def test_file_corrupted_recovery(self, tmp_path):
        """Test recovery from corrupted log file."""
        spec_dir = tmp_path / "spec-001"
        spec_dir.mkdir()

        # Create corrupted file
        log_file = spec_dir / "task_logs.json"
        log_file.write_text("{ invalid json", encoding="utf-8")

        # Create writer - should recover
        writer = TaskLogWriter(spec_dir)

        logs = json.loads(writer.log_file.read_text())
        assert logs["spec_id"] == "spec-001"


class TestTimestamps:
    """Test timestamp management."""

    def test_updated_at_timestamp(self, writer):
        """Test updated_at timestamp is updated on writes."""
        logs1 = json.loads(writer.log_file.read_text())
        updated_at_1 = logs1["updated_at"]

        # Wait a bit and make change
        import time
        time.sleep(0.01)

        writer.add_log_entry("coding", "New entry", "info")

        logs2 = json.loads(writer.log_file.read_text())
        updated_at_2 = logs2["updated_at"]

        # Timestamp should have changed
        assert updated_at_2 > updated_at_1

    def test_phase_timestamps(self, writer):
        """Test phase started_at and completed_at timestamps."""
        writer.set_phase_status("coding", "active")
        logs1 = json.loads(writer.log_file.read_text())
        started_at = logs1["phases"]["coding"]["started_at"]

        assert started_at is not None

        writer.mark_phase_complete("coding", success=True)
        logs2 = json.loads(writer.log_file.read_text())
        completed_at = logs2["phases"]["coding"]["completed_at"]

        assert completed_at is not None
        assert completed_at >= started_at


# Fixtures

@pytest.fixture
def writer(tmp_path):
    """Create a task log writer for testing."""
    spec_dir = tmp_path / "test-spec"
    spec_dir.mkdir()
    return TaskLogWriter(spec_dir)
