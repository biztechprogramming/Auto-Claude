# Docker Workflow Design Specification

## Overview

The Docker isolation pipeline uses a configurable workflow system where each step runs in a dedicated container with HTTP-based communication. The workflow tracks state in `task_logs.json` to enable resumability without repeating completed steps.

## Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Workflow Orchestrator                         │
│                   (docker_strategy.py)                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  Load Workflow  │
                    │  Configuration  │
                    └─────────────────┘
                              │
                              ▼
        ┌─────────────────────────────────────────┐
        │  For each step in workflow (sequential)  │
        └─────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ Check if step   │
                    │ already complete│
                    └─────────────────┘
                       │           │
                  Yes  │           │ No
                       ▼           ▼
                    [Skip]    [Execute Step]
                                   │
                                   ▼
                         ┌─────────────────┐
                         │ Start Container  │
                         │ Stream Logs      │
                         └─────────────────┘
                                   │
                         ┌─────────┴─────────┐
                         │                   │
                    Success            Failure
                         │                   │
                         ▼                   ▼
                  Mark Complete    Check if accepts
                  Continue to         feedback
                  next step               │
                                   ┌──────┴──────┐
                                   │             │
                                  Yes           No
                                   │             │
                              Retry Loop    Mark Failed
                              (max 3x)      Exit Pipeline
```

## Workflow State Machine

### States

1. **PENDING** - Step not yet executed
2. **ACTIVE** - Step currently running
3. **COMPLETED** - Step finished successfully
4. **FAILED** - Step failed (terminal state)
5. **SKIPPED** - Step skipped (already completed)

### State Transitions

```
PENDING → ACTIVE → COMPLETED → [Next Step]
                ↓
              FAILED → [Retry if accepts_feedback] → ACTIVE
                    → [Exit pipeline if no retry]

PENDING → SKIPPED → [Next Step] (if skip_if_complete=true and already done)
```

## Task Log Structure

**Location**: `.auto-claude/specs/{spec-name}/task_logs.json`

```json
{
  "spec_id": "002-feature-name",
  "created_at": "2025-12-28T19:30:00",
  "updated_at": "2025-12-28T19:35:00",
  "workflow_status": "in_progress",  // NEW: Overall workflow status
  "current_step": "validation",       // NEW: Current step being executed
  "iteration": 1,                     // NEW: Current retry iteration
  "phases": {
    "planning": {
      "status": "completed",
      "started_at": "2025-12-28T19:30:00",
      "completed_at": "2025-12-28T19:30:30",
      "entries": [...]
    },
    "coding": {
      "status": "completed",
      "started_at": "2025-12-28T19:31:00",
      "completed_at": "2025-12-28T19:33:00",
      "entries": [...]
    },
    "validation": {
      "status": "active",
      "started_at": "2025-12-28T19:34:00",
      "completed_at": null,
      "entries": [...]
    },
    "testing": {
      "status": "pending",
      "started_at": null,
      "completed_at": null,
      "entries": []
    }
  }
}
```

## Workflow Execution Flow

### Phase 1: Initialization

```python
# Load workflow configuration
workflow = get_workflow()

# Initialize state tracking
workflow_status = "planning"
iteration = 0
accumulated_comments = []
```

### Phase 2: Planning (Pre-Workflow)

**Status Updates**:
- `workflow_status = "planning"`
- Log planning subtasks

**No container execution** - just status updates.

### Phase 3: Workflow Execution Loop

```python
while iteration < max_iterations:  # Default: 3
    iteration += 1

    for step in workflow:
        # Step 1: Check if skip
        if should_skip(step):
            mark_step_skipped(step)
            continue

        # Step 2: Update status to active
        set_workflow_status(step.kanban_status)
        set_phase_status(step.log_phase, "active")

        # Step 3: Execute container
        result = execute_container_step(step)

        # Step 4: Handle result
        if result.success:
            # Success path
            set_phase_status(step.log_phase, "completed")
            continue_to_next_step()
        else:
            # Failure path
            handle_step_failure(step, result)

    # Step 5: Check overall completion
    if all_steps_completed():
        set_workflow_status("ready_for_review")
        return SUCCESS

# Max iterations reached
set_workflow_status("failed")
return FAILURE
```

## Detailed Step Execution

### Step Execution Pseudocode

```python
def execute_container_step(step):
    """
    Execute a single workflow step.

    Returns:
        ContainerResult with success/failure and optional comments
    """

    # 1. Check if step should be skipped
    if iteration == 1 and step.skip_if_complete:
        if is_phase_complete(step.log_phase):
            log_info(f"{step.description} - already completed, skipping")
            return create_mock_success_result(step)

    # 2. Update Kanban status
    if iteration == 1:
        update_kanban(step.kanban_status, step.description)
    else:
        update_kanban(step.kanban_status,
                     f"{step.description} (retry {iteration}/{max_iterations})")

    # 3. Set phase to active in task_logs.json
    task_log_writer.set_phase_status(step.log_phase, "active")

    # 4. Prepare task data
    task_description = step.task_template.format(spec_name=spec_name)
    feedback_str = format_feedback_comments(accumulated_comments) if step.accepts_feedback else None

    # 5. Execute container via HTTP
    result = await orchestrator._run_container_http(
        role=step.role,
        spec_name=spec_name,
        branch_name=branch_name,
        task_description=task_description,
        feedback_comments=feedback_str,
    )

    # 6. Process result
    if result.success:
        task_log_writer.mark_phase_complete(step.log_phase, success=True)
        update_kanban(step.kanban_status, f"✓ {step.description} completed")
    else:
        # Don't mark as failed yet - let failure handler decide
        pass

    return result
```

### Failure Handling

```python
def handle_step_failure(step, result):
    """
    Handle step failure with appropriate retry logic.

    Returns:
        CONTINUE_LOOP - retry the workflow
        EXIT_FAILED - fail the entire pipeline
    """

    # Case 1: Step accepts feedback AND we have iterations left
    if step.accepts_feedback and iteration < max_iterations:
        # Collect feedback comments for next iteration
        accumulated_comments.extend(result.comments)

        # Log the failure reason
        task_log_writer.add_log_entry(
            step.log_phase,
            f"{step.description} failed: {len(result.comments)} issues found",
            "error"
        )

        # Update Kanban to needs_revision
        update_kanban("needs_revision",
                     f"{step.description} failed: {len(result.comments)} issues found")

        # Mark phase as failed (will retry)
        task_log_writer.mark_phase_complete(step.log_phase, success=False)

        # Break inner loop to retry from beginning
        return CONTINUE_LOOP

    # Case 2: No retry available - fail permanently
    else:
        # Log the error
        task_log_writer.add_log_entry(
            step.log_phase,
            f"{step.description} failed",
            "error"
        )

        # Mark phase as permanently failed
        task_log_writer.mark_phase_complete(step.log_phase, success=False)

        # Update workflow status to failed
        update_kanban("failed", f"{step.description} failed")

        # Exit the pipeline
        return EXIT_FAILED
```

## Status Values

### Workflow-Level Status (`workflow_status`)

| Status | Meaning | When Set |
|--------|---------|----------|
| `planning` | Pre-workflow planning phase | At workflow start |
| `coding` | Developer container executing | When coding step starts |
| `ai_review` | Evaluator container executing | When validation step starts |
| `ai_testing` | QA container executing | When testing step starts |
| `needs_revision` | Step failed, will retry | When step fails and accepts feedback |
| `ready_for_review` | All steps passed | When all steps complete successfully |
| `failed` | Workflow failed permanently | When step fails with no retry, or max iterations reached |

### Phase-Level Status (`phases.{phase}.status`)

| Status | Meaning | When Set |
|--------|---------|----------|
| `pending` | Not yet executed | Initial state |
| `active` | Currently executing | When container starts |
| `completed` | Finished successfully | When container returns success |
| `failed` | Finished with errors | When container returns failure |

## Failure Conditions

### 1. Container Startup Failure

**Condition**: Docker container fails to start or API doesn't become ready

**Handling**:
```python
try:
    container_id = client.start_container()
    if not client.wait_for_ready(timeout=30):
        raise RuntimeError(f"{role} container API did not become ready")
except Exception as e:
    task_log_writer.add_log_entry(phase, f"Container error: {str(e)}", "error")
    task_log_writer.mark_phase_complete(phase, success=False)
    update_kanban("failed", f"Failed to start {step.description}")
    return FAILURE
```

**Status Updates**:
- `workflow_status` → `"failed"`
- `phase.status` → `"failed"`
- **No retry**

### 2. Container Execution Failure

**Condition**: Container runs but task fails (exit code != 0)

**Handling**:
```python
result = await client.wait_for_completion(timeout=600)
# Raises RuntimeError if status == "failed"
```

**For steps with `accepts_feedback=True` (Developer)**:
- Collect feedback comments
- Mark phase as `"failed"`
- Set `workflow_status` → `"needs_revision"`
- Continue to next iteration (retry)

**For steps with `accepts_feedback=False` (Evaluator, QA)**:
- Mark phase as `"failed"`
- Set `workflow_status` → `"failed"`
- Exit pipeline immediately

### 3. Container Timeout

**Condition**: Container doesn't complete within timeout (default: 600s)

**Handling**:
```python
try:
    result = await client.wait_for_completion(timeout=600)
except TimeoutError:
    task_log_writer.add_log_entry(phase, "Container timeout", "error")
    task_log_writer.mark_phase_complete(phase, success=False)
    update_kanban("failed", "Container timeout")
    return FAILURE
```

**Status Updates**:
- `workflow_status` → `"failed"`
- `phase.status` → `"failed"`
- **No retry**

### 4. Max Iterations Reached

**Condition**: Feedback loop exceeds max_iterations (default: 3)

**Handling**:
```python
# After loop exits
if not all_steps_completed:
    update_kanban("failed",
                 f"Max iterations ({max_iterations}) reached - needs manual review")
    return FAILURE
```

**Status Updates**:
- `workflow_status` → `"failed"`
- Current `phase.status` → `"failed"`
- **No retry**

### 5. Validation/Review Rejection

**Condition**: Evaluator returns `success=False` with comments

**Handling**:
```python
if not eval_result.success:
    accumulated_comments.extend(eval_result.comments)
    task_log_writer.add_log_entry(
        "validation",
        f"Code review rejected: {len(eval_result.comments)} issues",
        "error"
    )
    update_kanban("needs_revision",
                 f"AI Review rejected: {len(eval_result.comments)} issues found")
    # Continue loop to retry developer
```

**Status Updates**:
- `workflow_status` → `"needs_revision"`
- `validation.status` → `"failed"`
- Loop continues (retry from developer step)

### 6. Testing Failure

**Condition**: QA returns `success=False` with test failures

**Handling**: Same as validation rejection (retry from developer)

**Status Updates**:
- `workflow_status` → `"needs_revision"`
- `testing.status` → `"failed"`
- Loop continues (retry from developer step)

## Resumability Logic

### Skip Condition

A step is skipped when **ALL** of the following are true:

1. `iteration == 1` (first iteration only)
2. `step.skip_if_complete == True` (configured in workflow)
3. `task_logs.json` shows `phases[step.log_phase].status == "completed"`

### Example: Resume After Validation Failure

**Initial Run**:
```
Coding: SUCCESS → status=completed
Validation: FAILURE → status=failed, workflow_status=failed
```

**Resume (re-run same spec)**:
```
Iteration 1:
  Coding: SKIPPED (already completed)
  Validation: EXECUTE (failed previously, so retry)
  Testing: EXECUTE (if validation succeeds)
```

### Example: Resume After Max Iterations

**Initial Run**:
```
Iteration 1: Coding SUCCESS → Validation REJECT → retry
Iteration 2: Coding SUCCESS → Validation REJECT → retry
Iteration 3: Coding SUCCESS → Validation REJECT → FAILED (max iterations)
```

**Status**:
- `coding.status` = `"completed"` (last success)
- `validation.status` = `"failed"`
- `workflow_status` = `"failed"`

**Resume (re-run same spec)**:
```
Iteration 1:
  Coding: SKIPPED (already completed)
  Validation: EXECUTE (start fresh, iteration counter reset)
```

## Complete Workflow Status Matrix

| Scenario | Coding Status | Validation Status | Testing Status | Workflow Status | Action |
|----------|---------------|-------------------|----------------|-----------------|--------|
| All succeed | completed | completed | completed | ready_for_review | ✅ Done |
| Dev fails (no retry) | failed | pending | pending | failed | ❌ Exit |
| Dev fails (retry available) | failed | pending | pending | needs_revision | 🔄 Retry |
| Validation fails | completed | failed | pending | needs_revision | 🔄 Retry from dev |
| Testing fails | completed | completed | failed | needs_revision | 🔄 Retry from dev |
| Max iterations | completed | failed | pending | failed | ❌ Exit |
| Container timeout | active | pending | pending | failed | ❌ Exit |
| Container won't start | failed | pending | pending | failed | ❌ Exit |

## Implementation Checklist

### Current State ✅
- [x] Workflow configuration system
- [x] Step-by-step execution loop
- [x] Phase status tracking in task_logs.json
- [x] Skip logic for completed steps
- [x] Feedback loop for developer step
- [x] HTTP-based container communication
- [x] Log streaming to UI

### Needed Enhancements
- [ ] Add `workflow_status`, `current_step`, `iteration` to task_logs.json
- [ ] Persist workflow state between runs
- [ ] Add timeout handling with proper status updates
- [ ] Add container startup failure handling
- [ ] Create comprehensive status update functions
- [ ] Add workflow status API endpoint for UI
- [ ] Create workflow status dashboard in UI

## API Endpoints

### Workflow Control

```python
# Get current workflow status
GET /api/workflow/{spec_name}/status
Response: {
  "workflow_status": "ai_review",
  "current_step": "validation",
  "iteration": 1,
  "phases": {...}
}

# Reset workflow (clear completed statuses)
POST /api/workflow/{spec_name}/reset
POST /api/workflow/{spec_name}/reset?phase=validation  # Reset specific phase

# Force retry from specific step
POST /api/workflow/{spec_name}/retry?from_step=validation
```

## Future Enhancements

1. **Parallel Step Execution**: Run independent steps simultaneously
2. **Conditional Steps**: Skip steps based on file types, project structure
3. **Custom Workflows**: Per-project or per-spec custom workflows
4. **Workflow Visualization**: UI dashboard showing workflow progress
5. **Step Dependencies**: Define dependencies between steps
6. **Partial Retry**: Retry only failed steps, not entire workflow
7. **Workflow Templates**: Predefined workflows for different project types
