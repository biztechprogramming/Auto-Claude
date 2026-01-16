# Docker Workflow Configuration Guide

## Overview

The Docker isolation pipeline is now fully configurable through a workflow system. Instead of hardcoded steps, the pipeline reads from a configurable array of workflow steps defined in `workflow_config.py`.

## Architecture

```
workflow_config.py
    ↓ defines steps
docker_strategy.py
    ↓ executes workflow
orchestrator.py
    ↓ runs each container with HTTP
base_server.py (in containers)
    ↓ processes requests
TaskLogWriter
    ↓ logs to UI
```

## Configuration File

**Location**: `apps/backend/core/isolation/workflow_config.py`

### WorkflowStep Definition

```python
@dataclass
class WorkflowStep:
    name: str                    # Unique identifier
    role: ContainerRole          # DEVELOPER, EVALUATOR, QA
    log_phase: str               # UI phase: 'coding', 'validation', 'testing'
    port: int                    # FastAPI port for this container
    description: str             # Human-readable description
    skip_if_complete: bool       # Skip if phase already completed
    accepts_feedback: bool       # Can receive feedback for retry
    kanban_status: str           # Status to show in UI
    task_template: str           # Task description template
```

### Default Workflow

```python
DEFAULT_WORKFLOW = [
    WorkflowStep(
        name="coding",
        role=ContainerRole.DEVELOPER,
        log_phase="coding",
        port=8001,
        description="Implement code changes",
        skip_if_complete=True,
        accepts_feedback=True,
        kanban_status="coding",
        task_template="Implement features for {spec_name}"
    ),
    WorkflowStep(
        name="code_review",
        role=ContainerRole.EVALUATOR,
        log_phase="validation",
        port=8002,
        description="Review code quality",
        skip_if_complete=True,
        accepts_feedback=False,
        kanban_status="ai_review",
        task_template="Review code quality for {spec_name}"
    ),
    WorkflowStep(
        name="testing",
        role=ContainerRole.QA,
        log_phase="testing",
        port=8003,
        description="Run automated tests",
        skip_if_complete=True,
        accepts_feedback=False,
        kanban_status="ai_testing",
        task_template="Run automated tests for {spec_name}"
    ),
]
```

## How It Works

### 1. Workflow Execution

The `docker_strategy.py` now executes steps generically:

```python
workflow = get_workflow()

for step in workflow:
    # Skip if already complete
    if step.skip_if_complete and self._is_phase_complete(spec_name, step.log_phase):
        continue

    # Run container
    result = await orchestrator._run_container_http(
        role=step.role,
        spec_name=spec_name,
        branch_name=branch_name,
        task_description=step.task_template.format(spec_name=spec_name),
        feedback_comments=accumulated_comments if step.accepts_feedback else [],
    )

    # Handle result...
```

### 2. State Tracking

- **Skip completed steps**: Checks `task_logs.json` to see if `step.log_phase` is marked as "completed"
- **Simple and fast**: No complex git operations, just reads existing log file

### 3. Feedback Loops

- Steps with `accepts_feedback=True` (like Developer) will retry on failure
- Other steps fail the pipeline immediately
- Max 3 iterations by default

## Adding a New Step

### Example: Add a Security Scan Step

1. **Define the step** in `workflow_config.py`:

```python
WorkflowStep(
    name="security_scan",
    role=ContainerRole.SECURITY,  # Add to ContainerRole enum first
    log_phase="security",          # Add to TaskLogPhase type in frontend
    port=8004,
    description="Run security analysis",
    skip_if_complete=True,
    accepts_feedback=False,
    kanban_status="security_scan",
    task_template="Scan security for {spec_name}"
)
```

2. **Create the container**:
   - Add `Dockerfile.security` in `apps/backend/docker/`
   - Add `security_server.py` in `apps/backend/docker/api/`
   - Inherit from `BaseContainerServer`
   - Implement `_run_task()` method

3. **Update types**:
   - Add `ContainerRole.SECURITY` to `base.py`
   - Add `'security'` to `TaskLogPhase` in frontend types
   - Add `security: TaskPhaseLog` to `TaskLogs` interface

4. **Update UI** (optional):
   - Add phase label, icon, color in `TaskLogs.tsx`

5. **Build the image**:
```bash
docker build -f docker/Dockerfile.security -t auto-claude-security:latest .
```

That's it! The workflow will automatically:
- Execute your new step in sequence
- Stream logs to the UI
- Track completion status
- Skip on re-runs if already complete

## Benefits

✅ **Easy to extend**: Add new steps by editing one config file
✅ **Consistent logging**: All containers use same HTTP/logging pattern
✅ **Flexible order**: Rearrange steps by changing array order
✅ **State tracking**: Built-in skip logic using `task_logs.json`
✅ **No code changes**: Adding steps doesn't require modifying orchestrator

## Files Modified

- `apps/backend/core/isolation/workflow_config.py` - **NEW** - Workflow configuration
- `apps/backend/core/isolation/docker_strategy.py` - Uses workflow config
- `apps/backend/core/isolation/orchestrator.py` - Gets port/phase from config
- `apps/backend/docker/api/evaluator_server.py` - Better error logging
- `apps/backend/docker/api/qa_server.py` - Better error logging

## Future Enhancements

- Load workflow from JSON/YAML config file
- Per-project custom workflows
- Conditional steps (skip based on file types, etc.)
- Parallel step execution (run multiple containers simultaneously)
