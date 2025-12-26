# Kanban Status Flow - Docker Isolation

## Required Kanban Columns

Your Kanban board should have these columns to match the Docker pipeline:

| Column | Status Key | Description |
|--------|-----------|-------------|
| **Planning** | `planning` | Creating implementation plan with subtasks |
| **Coding** | `coding` | Developer container implementing features |
| **AI Review** | `ai_review` | Evaluator container reviewing code quality |
| **AI Testing** | `ai_testing` | QA container running automated tests |
| **Needs Revision** | `needs_revision` | Failed checks, requires fixes |
| **Ready for Review** | `ready_for_review` | All checks passed, awaiting human review |
| **Failed** | `failed` | Max iterations reached or critical error |

---

## Status Flow

### Happy Path (All Checks Pass)

```
planning → coding → ai_review → ai_testing → ready_for_review
```

**Example messages:**
1. `planning`: "Creating implementation plan"
2. `planning`: "Plan: 5 subtasks"
3. `coding`: "Implementing features..."
4. `coding`: "Completed - commit abc1234"
5. `ai_review`: "Reviewing code quality..."
6. `ai_review`: "✓ Code quality approved"
7. `ai_testing`: "Running automated tests..."
8. `ai_testing`: "✓ All tests passed"
9. `ready_for_review`: "All checks passed - ready for human review"

### Feedback Loop (Review Fails)

```
planning → coding → ai_review → needs_revision → coding → ai_review → ai_testing → ready_for_review
                     ↓                              ↑
                     └──────────────────────────────┘
                          (feedback loop)
```

**Example messages:**
1. `planning`: "Creating implementation plan"
2. `coding`: "Implementing features..."
3. `ai_review`: "Reviewing code quality..."
4. `needs_revision`: "AI Review rejected: 3 issues found"
5. `coding`: "Addressing feedback (iteration 2/3)"
6. `ai_review`: "Reviewing code quality..."
7. `ai_review`: "✓ Code quality approved"
8. `ai_testing`: "Running automated tests..."
9. `ai_testing`: "✓ All tests passed"
10. `ready_for_review`: "All checks passed - ready for human review"

### Feedback Loop (Testing Fails)

```
planning → coding → ai_review → ai_testing → needs_revision → coding → ...
                                    ↓                             ↑
                                    └─────────────────────────────┘
                                         (feedback loop)
```

**Example messages:**
1. `planning`: "Creating implementation plan"
2. `coding`: "Implementing features..."
3. `ai_review`: "Reviewing code quality..."
4. `ai_review`: "✓ Code quality approved"
5. `ai_testing`: "Running automated tests..."
6. `needs_revision`: "AI Testing failed: 2 test failures"
7. `coding`: "Addressing feedback (iteration 2/3)"
8. `ai_review`: "Reviewing code quality..."
9. `ai_review`: "✓ Code quality approved"
10. `ai_testing`: "Running automated tests..."
11. `ai_testing`: "✓ All tests passed"
12. `ready_for_review`: "All checks passed - ready for human review"

### Max Iterations Reached

```
planning → coding → ai_review → needs_revision → coding → ai_review → needs_revision → failed
                                    ↓                ↑        ↓            ↑
                                    └────────────────┘        └────────────┘
                                    (iteration 1)            (iteration 2)
                                                            (iteration 3 = max)
```

**Example messages:**
1. `planning`: "Creating implementation plan"
2. `coding`: "Implementing features..."
3. `ai_review`: "Reviewing code quality..."
4. `needs_revision`: "AI Review rejected: 3 issues found"
5. `coding`: "Addressing feedback (iteration 2/3)"
6. `ai_review`: "Reviewing code quality..."
7. `needs_revision`: "AI Review rejected: 2 issues found"
8. `coding`: "Addressing feedback (iteration 3/3)"
9. `ai_review`: "Reviewing code quality..."
10. `needs_revision`: "AI Review rejected: 1 issue found"
11. `failed`: "Max iterations (3) reached - needs manual review"

---

## Integration Example

### Python Backend

```python
from pathlib import Path
from core.isolation.factory import IsolationFactory

def on_status_change(spec_name: str, status: str, message: str = ""):
    """
    Callback for pipeline status updates.

    Args:
        spec_name: Name of the spec (e.g., "001-auth")
        status: Kanban column key (e.g., "coding", "ai_review", "ai_testing")
        message: Human-readable status message
    """
    print(f"[{spec_name}] {status}: {message}")

    # Update your Kanban board
    update_kanban_card(spec_name, column=status, message=message)

    # Update database
    update_spec_status(spec_name, status=status, message=message)

    # Send webhook/notification
    notify_status_change(spec_name, status, message)

# Run pipeline with status tracking
strategy = IsolationFactory.create(Path("."), method="docker")
strategy.setup()

plan = {
    "subtasks": [
        {"id": 1, "description": "Create User model"},
        {"id": 2, "description": "Add authentication endpoints"},
        {"id": 3, "description": "Write tests"},
    ]
}

success = await strategy.run_pipeline(
    spec_name="001-auth",
    plan=plan,
    on_status_change=on_status_change
)
```

### Expected Console Output

```
[001-auth] planning: Creating implementation plan
[001-auth] planning: Plan: 3 subtasks
[001-auth] coding: Implementing features...
[001-auth] coding: Completed - commit abc1234
[001-auth] ai_review: Reviewing code quality...
[001-auth] ai_review: ✓ Code quality approved
[001-auth] ai_testing: Running automated tests...
[001-auth] ai_testing: ✓ All tests passed
[001-auth] ready_for_review: All checks passed - ready for human review
```

---

## Status Details

### Planning Phase
- **Status**: `planning`
- **Duration**: Usually < 1 second (plan already created)
- **Actions**: Shows subtask count if available
- **Next**: Always proceeds to `coding`

### Coding Phase
- **Status**: `coding`
- **Duration**: 1-10 minutes (varies by task complexity)
- **Actions**:
  - First iteration: "Implementing features..."
  - Subsequent: "Addressing feedback (iteration X/Y)"
  - On success: Shows commit SHA
- **Next**: `ai_review` (if successful) or `failed` (if error)

### AI Review Phase
- **Status**: `ai_review`
- **Duration**: 30 seconds - 2 minutes
- **Actions**:
  - Evaluator container reviews code quality
  - Checks best practices, security, patterns
- **Next**:
  - `ai_testing` (if approved)
  - `needs_revision` (if rejected, loops to `coding`)

### AI Testing Phase
- **Status**: `ai_testing`
- **Duration**: 1-5 minutes (depends on test suite)
- **Actions**:
  - QA container runs Playwright tests
  - Runs unit/integration tests
  - Validates functionality
- **Next**:
  - `ready_for_review` (if passed)
  - `needs_revision` (if failed, loops to `coding`)

### Needs Revision
- **Status**: `needs_revision`
- **Duration**: Immediate (just sets status)
- **Actions**: Collects feedback comments from evaluator or QA
- **Next**: Loops back to `coding` (if iterations < max)

### Ready for Review
- **Status**: `ready_for_review`
- **Duration**: Terminal state (waits for human)
- **Actions**: All automated checks passed
- **Next**: Human reviews and either:
  - Approves → `merge_changes()`
  - Rejects → Manual intervention needed

### Failed
- **Status**: `failed`
- **Duration**: Terminal state
- **Actions**: Max iterations reached or critical error
- **Next**: Requires manual debugging/fixes

---

## Comparison: Docker vs Worktree

### Docker Mode Statuses
```
planning → coding → ai_review → ai_testing → ready_for_review
```

### Worktree Mode Statuses (old)
```
planning → coding → qa_review → qa_fixing → ready_for_review
```

**Key Differences:**
- Docker splits review into **AI Review** (code quality) and **AI Testing** (functional tests)
- Worktree combines into single QA phase
- Docker provides more granular visibility
- Docker shows iteration count during feedback loops

---

## UI Integration Tips

### Progress Indicators

```javascript
// Map status to progress percentage
const progressMap = {
  'planning': 10,
  'coding': 30,
  'ai_review': 60,
  'ai_testing': 80,
  'ready_for_review': 100,
  'needs_revision': 50,  // Mid-loop
  'failed': 0
};

function updateProgressBar(status) {
  const progress = progressMap[status] || 0;
  progressBar.style.width = `${progress}%`;
}
```

### Status Icons

```javascript
const statusIcons = {
  'planning': '📋',
  'coding': '⚙️',
  'ai_review': '🔍',
  'ai_testing': '🧪',
  'ready_for_review': '✅',
  'needs_revision': '⚠️',
  'failed': '❌'
};
```

### Live Updates

```javascript
// WebSocket or Server-Sent Events
function onStatusChange(event) {
  const { spec_name, status, message } = event;

  // Update Kanban card
  moveCard(spec_name, status);

  // Update message
  updateCardMessage(spec_name, message);

  // Show notification
  if (status === 'ready_for_review') {
    notify(`${spec_name} is ready for your review!`);
  }
}
```

---

## Summary

✅ **New Column Required**: Add "AI Testing" column to your Kanban
✅ **Detailed Progress**: Shows planning, coding, review, and testing phases
✅ **Feedback Visibility**: Clear messages when checks fail
✅ **Iteration Tracking**: Shows current/max iterations during loops
✅ **Commit References**: Shows commit SHA after coding completes

Your Kanban board now has complete visibility into the Docker pipeline! 🎉
