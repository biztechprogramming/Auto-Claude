# Docker Container Logging Implementation

## Summary

Implemented real-time logging for Docker containers using the **Observer Pattern** to stream container output to structured JSON files that the UI watches and displays.

## Architecture

### Observer Pattern Implementation

```
Docker Container (Observable)
    ↓ stdout/stderr
Background Thread (Observer)
    ↓ parses lines
TaskLogWriter (Subject)
    ↓ writes JSON
task_logs.json
    ↓ watched by
UI (Consumer)
```

## Components Created

### 1. TaskLogWriter Class (`apps/backend/core/task_log_writer.py`)

**Purpose**: Observer that converts raw Docker logs into structured JSON for UI consumption

**Key Methods**:
- `set_phase_status(phase, status)` - Update phase status (pending/active/completed/failed)
- `add_log_entry(phase, content, type, detail)` - Add structured log entry
- `observe_container_log(phase, log_line)` - Parse container output and create entries
- `mark_phase_complete(phase, success)` - Mark phase as done

**Log Entry Types**:
- `info` - INFO level messages
- `error` - ERROR level messages
- `success` - Success messages
- `text` - General text output

### 2. Integration in Orchestrator (`apps/backend/core/isolation/orchestrator.py`)

**Changes Made**:

1. **Initialize TaskLogWriter** (lines 174-190):
```python
from core.task_log_writer import TaskLogWriter
spec_dir = self.project_dir / ".auto-claude" / "specs" / spec_name
log_writer = TaskLogWriter(spec_dir)

# Map container role to UI phase
phase_map = {
    ContainerRole.DEVELOPER: "coding",
    ContainerRole.EVALUATOR: "coding",
    ContainerRole.QA: "validation",
}
phase = phase_map[role]

# Set phase to active
log_writer.set_phase_status(phase, "active")
```

2. **Stream Docker Logs** (lines 200-222):
```python
# Start docker logs -f and pipe to observer
log_stream_process = subprocess.Popen(
    ["docker", "logs", "-f", container_id],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1  # Line buffered
)

# Background thread observes logs in real-time
def observe_logs():
    for line in log_stream_process.stdout:
        log_writer.observe_container_log(phase, line.rstrip())

log_thread = threading.Thread(target=observe_logs, daemon=True)
log_thread.start()
```

3. **Mark Phase Complete** (lines 256, 270):
```python
# On success
log_writer.mark_phase_complete(phase, success=True)

# On failure
log_writer.mark_phase_complete(phase, success=False)
```

4. **Cleanup** (lines 288-298):
```python
finally:
    if log_stream_process:
        log_stream_process.terminate()
        log_stream_process.wait(timeout=5)
```

## Output Format

### task_logs.json Structure

Located at: `.auto-claude/specs/{spec-name}/task_logs.json`

```json
{
  "spec_id": "002-create-hello-txt",
  "created_at": "2025-12-27T19:30:00",
  "updated_at": "2025-12-27T19:35:00",
  "phases": {
    "planning": {
      "status": "completed",
      "entries": []
    },
    "coding": {
      "status": "active",
      "entries": [
        {
          "timestamp": "2025-12-27T19:31:00",
          "type": "info",
          "content": "Cloning repository: https://github.com/..."
        },
        {
          "timestamp": "2025-12-27T19:31:05",
          "type": "info",
          "content": "POST /clone → 200"
        },
        {
          "timestamp": "2025-12-27T19:31:10",
          "type": "info",
          "content": "Modified README.md"
        }
      ]
    },
    "validation": {
      "status": "pending",
      "entries": []
    }
  }
}
```

## How UI Consumes Logs

### Existing UI Components (No Changes Needed)

1. **TaskLogService** (`apps/frontend/src/main/task-log-service.ts`)
   - Already watches `task_logs.json` for changes
   - Polls file every 1 second
   - Emits updates to renderer

2. **TaskLogs Component** (`apps/frontend/src/renderer/components/task-detail/TaskLogs.tsx`)
   - Already renders phase-based collapsible logs
   - Shows status badges (Running/Complete/Failed)
   - Displays log entries with icons and formatting

## Current Implementation Status

### ✅ Implemented for Coding Phase

- Developer container logs stream to `task_logs.json` under `coding` phase
- Evaluator container also writes to `coding` phase (review is part of coding)
- Real-time updates via background thread
- Proper cleanup on container completion/failure

### ❌ Not Yet Implemented for Validation Phase

The QA container is mapped to the `validation` phase but needs the same treatment.

## TODO: Add AI Testing/QA Section to UI

### Required Changes

#### 1. Backend - Already Done ✅
- QA container already mapped to "validation" phase
- TaskLogWriter already supports all 3 phases (planning, coding, validation)
- No backend changes needed

#### 2. Frontend - Status Display

**Current Status**: The UI already shows a "Validation" section in TaskLogs.tsx (line 136-146)

```tsx
{(['planning', 'coding', 'validation'] as TaskLogPhase[]).map((phase) => (
  <PhaseLogSection
    key={phase}
    phase={phase}
    phaseLog={phaseLogs.phases[phase]}
    isExpanded={expandedPhases.has(phase)}
    onToggle={() => onTogglePhase(phase)}
  />
))}
```

**Current Labels** (line 39-43):
```tsx
const PHASE_LABELS: Record<TaskLogPhase, string> = {
  planning: 'Planning',
  coding: 'Coding',
  validation: 'Validation'
};
```

**Suggested Change** - Make it clearer this is AI-driven:
```tsx
const PHASE_LABELS: Record<TaskLogPhase, string> = {
  planning: 'Planning',
  coding: 'Coding',
  validation: 'AI Testing'  // or 'QA Testing'
};
```

**Icon Change** (line 45-49):
```tsx
const PHASE_ICONS: Record<TaskLogPhase, typeof Pencil> = {
  planning: Pencil,
  coding: FileCode,
  validation: FlaskConical  // Already using flask icon, perfect for testing
};
```

### Summary of Frontend Changes Needed

**File**: `apps/frontend/src/renderer/components/task-detail/TaskLogs.tsx`

**Change**: Line 42 - Update label
```tsx
// FROM:
validation: 'Validation'

// TO:
validation: 'AI Testing'
```

**That's it!** Everything else already works because:
- UI already watches all 3 phases
- Backend already writes QA logs to validation phase
- Collapsible sections already render automatically
- Status badges already work for all phases

## Testing

1. Set `ISOLATION_METHOD=docker` in `.env`
2. Run a task
3. Watch `.auto-claude/specs/{spec}/task_logs.json` get created and updated
4. See real-time logs in UI under "Coding" section
5. When QA runs, see logs under "AI Testing" section

## Design Pattern Benefits

- **Observer Pattern**: Clean separation between log source and consumer
- **Single Responsibility**: TaskLogWriter only handles log formatting
- **Open/Closed**: Easy to add new log entry types without changing observer
- **Real-time**: Background thread provides immediate updates
- **Atomic Writes**: Temp file + rename prevents UI from seeing partial JSON
