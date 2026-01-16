# Phase-Based Architecture Guide

## Overview

Auto-Claude uses a **phase-based pipeline architecture** throughout its workflow system. This design pattern breaks complex processes into discrete, focused steps that can be executed, validated, and retried independently.

This document explains how the phase-based architecture works, where it's used, and how to apply it to new workflows.

## Core Concepts

### What is a Phase?

A **phase** is a single-purpose step in a larger workflow that:

1. **Has a clear input** - Data from previous phases or initial configuration
2. **Performs focused work** - One specific task (analyze, gather, write, validate)
3. **Produces artifacts** - JSON files, markdown documents, code changes
4. **Can be validated** - Output is checked for correctness/completeness
5. **Can retry** - If validation fails, the phase can run again
6. **Feeds forward** - Its output becomes input for the next phase

### Key Benefits

- **Modularity**: Each phase is independent and testable
- **Resumability**: Interrupted workflows can resume from the last completed phase
- **Adaptability**: Phases can be added, skipped, or reordered based on complexity
- **Reliability**: Failed phases retry without restarting the entire workflow
- **Traceability**: Each phase produces trackable artifacts
- **Feedback Loops**: Phases can loop back for iterative improvement

## Complexity-Adaptive Pipelines

Auto-Claude's most sophisticated use of phase-based architecture is **complexity adaptation** - the workflow changes based on task complexity.

### Complexity Tiers

The system analyzes tasks and selects one of three pipeline configurations:

#### SIMPLE (3 phases)
For straightforward tasks (1-2 files, no integrations):
```
Discovery → Historical Context → Quick Spec → Validation
```

**Example tasks**: "Fix button color", "Update text label", "Remove unused import"

#### STANDARD (6-7 phases)
For typical features (3-10 files, 1-2 services):
```
Discovery → Historical Context → Requirements → [Research] → Context → Spec Writing → Planning → Validation
```

**Example tasks**: "Add user profile page", "Implement email notifications", "Create REST API endpoint"

#### COMPLEX (8 phases)
For major features (10+ files, multiple services, external integrations):
```
Discovery → Historical Context → Requirements → Research → Context → Spec Writing → Self-Critique → Planning → Validation
```

**Example tasks**: "Add authentication system", "Integrate payment processing", "Implement real-time collaboration"

### Complexity Assessment

**Location**: [`apps/backend/spec/complexity.py`](../apps/backend/spec/complexity.py)

The system uses two methods to determine complexity:

1. **AI Assessment** (default) - Uses the `complexity_assessor.md` prompt to analyze:
   - Scope and file count
   - External integrations
   - Infrastructure changes
   - Knowledge requirements
   - Risk factors

2. **Heuristic Analysis** (fallback) - Keyword matching and pattern detection:
   - Simple keywords: "fix", "update", "change", "style"
   - Complex keywords: "integrate", "migrate", "docker", "authentication"
   - Service detection: "backend", "frontend", "worker", "database"

**Output**: `complexity_assessment.json` with recommended phases to run.

## Phase-Based Workflows in Auto-Claude

### 1. Spec Creation Pipeline

**Location**: [`apps/backend/spec/`](../apps/backend/spec/)

The specification creation process is organized into phase categories:

#### Phase Categories

**Discovery Phases** ([`phases/discovery_phases.py`](../apps/backend/spec/phases/discovery_phases.py))
- **Discovery**: Analyze project structure, detect frameworks, index codebase
- **Context**: Gather relevant files and patterns for the task

**Requirements Phases** ([`phases/requirements_phases.py`](../apps/backend/spec/phases/requirements_phases.py))
- **Requirements**: Extract and structure user requirements
- **Historical Context**: Retrieve relevant context from Graphiti memory (if enabled)
- **Research**: Validate external dependencies and integrations

**Spec Phases** ([`phases/spec_phases.py`](../apps/backend/spec/phases/spec_phases.py))
- **Quick Spec**: Fast specification for simple tasks
- **Spec Writing**: Comprehensive specification document
- **Self-Critique**: AI-powered review using extended thinking

**Planning Phases** ([`phases/planning_phases.py`](../apps/backend/spec/phases/planning_phases.py))
- **Planning**: Create subtask-based implementation plan
- **Validation**: Verify spec completeness and consistency

#### Phase Flow Example

```
Phase 1: Discovery
├── Prompt: discovery.md
├── Input: Project directory
├── Actions:
│   ├── Scan directory structure
│   ├── Detect frameworks (React, Python, Docker, etc.)
│   ├── Index important files
│   └── Identify project type (monorepo, library, app)
├── Output: project_index.json
└── Validation: Structure is valid JSON with required fields

Phase 2: Requirements
├── Prompt: spec_gatherer.md
├── Input: project_index.json + task_description
├── Actions:
│   ├── Extract user requirements
│   ├── Define acceptance criteria
│   ├── Identify constraints
│   └── List services involved
├── Output: requirements.json
└── Validation: All required fields present

Phase 3: Context
├── Prompt: context_gatherer.md
├── Input: requirements.json + project_index.json
├── Actions:
│   ├── Find relevant existing code
│   ├── Identify patterns to follow
│   ├── Locate similar implementations
│   └── Map file dependencies
├── Output: context.json
└── Validation: Sufficient context gathered

Phase 4: Spec Writing
├── Prompt: spec_writer.md
├── Input: requirements.json + context.json
├── Actions:
│   ├── Write comprehensive spec.md
│   ├── Define technical approach
│   ├── List files to modify
│   └── Specify testing strategy
├── Output: spec.md
└── Validation: Spec covers all requirements

Phase 5: Planning
├── Prompt: planner.md
├── Input: spec.md + context.json
├── Actions:
│   ├── Break into subtasks
│   ├── Define dependencies
│   ├── Estimate complexity
│   └── Order execution
├── Output: implementation_plan.json
└── Validation: Plan is actionable and complete
```

#### Orchestration

**Location**: [`apps/backend/spec/pipeline/orchestrator.py`](../apps/backend/spec/pipeline/orchestrator.py)

```python
class SpecOrchestrator:
    async def run(self):
        # 1. Assess complexity
        assessment = await self.assess_complexity()

        # 2. Get phases to run based on complexity
        phases = assessment.phases_to_run()

        # 3. Execute each phase
        for phase in phases:
            result = await self.executor.run_phase(phase)

            if not result.success:
                if result.retry_count < MAX_RETRIES:
                    # Retry the phase
                    result = await self.executor.run_phase(phase)
                else:
                    # Critical failure - abort
                    return False

            # Store artifacts for next phase
            self.artifacts[phase] = result

        return True
```

### 2. Implementation Pipeline

**Location**: [`apps/backend/agents/`](../apps/backend/agents/)

The implementation follows a **subtask-based workflow** with feedback loops:

```
1. Planning Session
   ├── Prompt: planner.md
   ├── Input: spec.md, requirements.json, context.json
   ├── Actions: Create subtask-based implementation plan
   ├── Output: implementation_plan.json
   └── Validates: Plan covers all acceptance criteria

2. Coding Sessions (per subtask)
   ├── Prompt: coder.md
   ├── Input: Subtask definition + session memory + plan
   ├── Actions: Implement code, write tests, commit changes
   ├── Output: Git commits + session notes
   └── Validates: Tests pass, subtask marked complete

3. Recovery Session (if stuck)
   ├── Prompt: coder_recovery.md
   ├── Input: Current state + error logs + stuck reasons
   ├── Actions: Analyze blockers, try alternative approach
   ├── Output: Recovery plan or code changes
   └── Validates: Progress resumes or escalates to human

4. QA Review Session
   ├── Prompt: qa_reviewer.md
   ├── Input: All code changes + acceptance criteria
   ├── Actions: Comprehensive validation of all criteria
   ├── Output: qa_report.md (APPROVED/REJECTED + issues)
   └── Validates: All criteria objectively assessed

5. QA Fixing Session (if rejected)
   ├── Prompt: qa_fixer.md
   ├── Input: qa_report.md issues list
   ├── Actions: Fix reported issues
   ├── Output: Code fixes + commits
   └── Feedback Loop: Returns to QA Review
```

#### Feedback Loop Pattern

The QA phase demonstrates the **feedback loop pattern**:

```
┌─────────────┐
│   Coding    │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────┐
│ QA Review   │─────▶│  APPROVED    │──▶ Done
└──────┬──────┘      └──────────────┘
       │
       │ REJECTED
       ▼
┌─────────────┐
│  QA Fixer   │
└──────┬──────┘
       │
       │ (loop back)
       └────────────▶ QA Review
```

**Max iterations**: Configurable (typically 3-5) before requiring human intervention.

### 3. Docker Multi-Container Pipeline

**Location**: [`apps/backend/core/isolation/docker_strategy.py`](../apps/backend/core/isolation/docker_strategy.py)

The Docker isolation mode uses a **multi-container feedback pipeline**:

```
┌──────────────────┐
│  Orchestrator    │ (Host process)
└────────┬─────────┘
         │
         ├─────────────────────────────────────┐
         │                                     │
         ▼                                     ▼
┌─────────────────┐                  ┌─────────────────┐
│   Developer     │                  │   Evaluator     │
│   Container     │◀─────feedback────│   Container     │
└────────┬────────┘                  └─────────────────┘
         │                                     ▲
         │ push changes                        │
         ▼                                     │
┌─────────────────┐                           │
│  QA Container   │───────feedback────────────┘
└─────────────────┘
```

#### Container Workflow

**1. Developer Container**
- **Input**: Spec, task description
- **Actions**: Clone repo, create branch, implement changes, run tests, push
- **Output**: Code changes pushed to Git
- **Feedback**: Receives comments from Evaluator and QA

**2. Evaluator Container**
- **Input**: Developer's code changes
- **Actions**: Code quality review, best practices check, security scan
- **Output**: APPROVED or REJECTED with feedback
- **Feedback Loop**: If rejected, sends comments back to Developer

**3. QA Container**
- **Input**: Evaluator-approved code
- **Actions**: Functional testing with Playwright, integration tests
- **Output**: PASSED or FAILED with test results
- **Feedback Loop**: If failed, sends issues back to Developer

**Max iterations**: 3 (configurable via `MAX_FEEDBACK_ITERATIONS`)

**Communication**: All containers share state via Git only (no shared volumes).

## Creating New Phase-Based Workflows

### Step 1: Define Your Phases

Create an enum and data structures:

```python
# workflows/my_workflow/phases.py
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

class MyWorkflowPhase(Enum):
    """Phases for my custom workflow."""
    INITIALIZATION = "initialization"
    ANALYSIS = "analysis"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    FINALIZATION = "finalization"

@dataclass
class PhaseResult:
    """Result of executing a single phase."""
    phase: MyWorkflowPhase
    success: bool
    output_file: Path | None
    artifacts: dict
    retry_count: int = 0
    error_message: str | None = None
```

### Step 2: Create Phase Executor

Implement the logic for running each phase:

```python
# workflows/my_workflow/executor.py
from pathlib import Path
from .phases import MyWorkflowPhase, PhaseResult

MAX_RETRIES = 3

class MyWorkflowExecutor:
    def __init__(self, project_dir: Path, output_dir: Path, run_agent_fn):
        self.project_dir = project_dir
        self.output_dir = output_dir
        self.run_agent_fn = run_agent_fn
        self.artifacts = {}

    async def run_phase(
        self,
        phase: MyWorkflowPhase,
        retry_count: int = 0
    ) -> PhaseResult:
        """Execute a single phase with validation and retry logic."""

        # 1. Load inputs from previous phases
        phase_inputs = self._load_phase_inputs(phase)

        # 2. Run agent with phase-specific prompt
        prompt_file = f"{phase.value}.md"
        success, output = await self.run_agent_fn(
            prompt_file,
            additional_context=phase_inputs
        )

        if not success:
            return PhaseResult(
                phase=phase,
                success=False,
                output_file=None,
                artifacts={},
                retry_count=retry_count,
                error_message="Agent execution failed"
            )

        # 3. Validate phase output
        is_valid, validation_error = self._validate_output(phase, output)

        if not is_valid:
            if retry_count < MAX_RETRIES:
                # Retry with context about what was wrong
                print(f"Phase {phase.value} validation failed: {validation_error}")
                print(f"Retrying... (attempt {retry_count + 1}/{MAX_RETRIES})")
                return await self.run_phase(phase, retry_count + 1)
            else:
                return PhaseResult(
                    phase=phase,
                    success=False,
                    output_file=None,
                    artifacts={},
                    retry_count=retry_count,
                    error_message=f"Validation failed after {MAX_RETRIES} retries: {validation_error}"
                )

        # 4. Save artifacts
        artifact_path = self._save_artifacts(phase, output)

        # 5. Store for next phase
        self.artifacts[phase.value] = output

        return PhaseResult(
            phase=phase,
            success=True,
            output_file=artifact_path,
            artifacts=output,
            retry_count=retry_count
        )

    def _load_phase_inputs(self, phase: MyWorkflowPhase) -> str:
        """Load inputs needed for this phase from previous phases."""
        context_parts = []

        if phase == MyWorkflowPhase.INITIALIZATION:
            context_parts.append(f"Project directory: {self.project_dir}")

        elif phase == MyWorkflowPhase.ANALYSIS:
            # Need initialization output
            if MyWorkflowPhase.INITIALIZATION.value in self.artifacts:
                init_data = self.artifacts[MyWorkflowPhase.INITIALIZATION.value]
                context_parts.append(f"Initialization data: {init_data}")

        elif phase == MyWorkflowPhase.TRANSFORMATION:
            # Need analysis output
            if MyWorkflowPhase.ANALYSIS.value in self.artifacts:
                analysis_data = self.artifacts[MyWorkflowPhase.ANALYSIS.value]
                context_parts.append(f"Analysis results: {analysis_data}")

        return "\n\n".join(context_parts)

    def _validate_output(self, phase: MyWorkflowPhase, output: dict) -> tuple[bool, str | None]:
        """Validate that phase output meets requirements."""

        # Phase-specific validation
        if phase == MyWorkflowPhase.INITIALIZATION:
            required_keys = ["workspace_path", "prerequisites_met"]
            for key in required_keys:
                if key not in output:
                    return False, f"Missing required key: {key}"

        elif phase == MyWorkflowPhase.ANALYSIS:
            if "findings" not in output or len(output["findings"]) == 0:
                return False, "No findings in analysis output"

        # Add more phase-specific validation...

        return True, None

    def _save_artifacts(self, phase: MyWorkflowPhase, output: dict) -> Path:
        """Save phase output to a file."""
        import json

        output_file = self.output_dir / f"{phase.value}.json"
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)

        return output_file
```

### Step 3: Create Orchestrator

Coordinate the execution of all phases:

```python
# workflows/my_workflow/orchestrator.py
from pathlib import Path
from .phases import MyWorkflowPhase
from .executor import MyWorkflowExecutor

class MyWorkflowOrchestrator:
    def __init__(
        self,
        project_dir: Path,
        output_dir: Path,
        run_agent_fn,
        skip_phases: list[str] | None = None
    ):
        self.project_dir = project_dir
        self.output_dir = output_dir
        self.executor = MyWorkflowExecutor(project_dir, output_dir, run_agent_fn)
        self.skip_phases = skip_phases or []

        # Define phase order
        self.phases = [
            MyWorkflowPhase.INITIALIZATION,
            MyWorkflowPhase.ANALYSIS,
            MyWorkflowPhase.TRANSFORMATION,
            MyWorkflowPhase.VALIDATION,
            MyWorkflowPhase.FINALIZATION,
        ]

    async def run(self) -> bool:
        """Execute all phases in order."""

        print(f"Starting workflow with {len(self.phases)} phases")

        for i, phase in enumerate(self.phases, 1):
            if phase.value in self.skip_phases:
                print(f"[{i}/{len(self.phases)}] Skipping {phase.value}")
                continue

            print(f"[{i}/{len(self.phases)}] Running phase: {phase.value}")

            result = await self.executor.run_phase(phase)

            if not result.success:
                print(f"❌ Phase {phase.value} failed: {result.error_message}")
                return False

            print(f"✅ Phase {phase.value} completed")
            if result.output_file:
                print(f"   Output saved to: {result.output_file}")

        print("✅ Workflow completed successfully")
        return True

    def get_artifacts(self) -> dict:
        """Get all artifacts produced by the workflow."""
        return self.executor.artifacts
```

### Step 4: Create Phase Prompts

Create a prompt file for each phase:

```markdown
<!-- prompts/initialization.md -->
# Initialization Phase

You are initializing a new workflow. Your tasks:

1. **Verify Prerequisites**
   - Check that required tools are installed
   - Validate input configuration
   - Ensure workspace is accessible

2. **Setup Workspace**
   - Create necessary directories
   - Initialize any required files
   - Set up logging

3. **Output Requirements**

Create a JSON file with:

```json
{
  "workspace_path": "/path/to/workspace",
  "prerequisites_met": true,
  "detected_tools": ["git", "docker", "python"],
  "issues": []
}
```

Save this to `initialization.json` in the output directory.
```

```markdown
<!-- prompts/analysis.md -->
# Analysis Phase

You are analyzing the project to gather information. Your tasks:

1. **Scan Project Structure**
   - Identify key files and directories
   - Detect frameworks and languages
   - Map dependencies

2. **Analyze Code Patterns**
   - Find common patterns
   - Identify potential issues
   - Document architecture

3. **Output Requirements**

Create a JSON file with:

```json
{
  "findings": [
    {
      "type": "pattern",
      "description": "Uses React with TypeScript",
      "confidence": 0.95
    }
  ],
  "architecture": "monorepo with apps/ and packages/",
  "recommendations": []
}
```

Save this to `analysis.json` in the output directory.
```

### Step 5: Integrate with Main System

Add your workflow to the main orchestration:

```python
# runners/my_workflow_runner.py
import asyncio
from pathlib import Path
from workflows.my_workflow import MyWorkflowOrchestrator
from client import ClaudeSDKClient

async def run_my_workflow(project_dir: Path, output_dir: Path):
    # Initialize Claude client
    client = ClaudeSDKClient(project_dir)

    async def run_agent_fn(prompt_file: str, additional_context: str = ""):
        # Wrapper for running agent sessions
        result = await client.run_session(
            prompt_file=prompt_file,
            context=additional_context
        )
        return result.success, result.output

    # Create and run orchestrator
    orchestrator = MyWorkflowOrchestrator(
        project_dir=project_dir,
        output_dir=output_dir,
        run_agent_fn=run_agent_fn
    )

    success = await orchestrator.run()

    if success:
        artifacts = orchestrator.get_artifacts()
        print(f"Workflow completed. Artifacts: {artifacts}")

    return success

if __name__ == "__main__":
    project_dir = Path.cwd()
    output_dir = project_dir / ".my-workflow" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    asyncio.run(run_my_workflow(project_dir, output_dir))
```

## Advanced Patterns

### Conditional Phase Execution

Skip phases based on conditions:

```python
class AdaptiveOrchestrator(MyWorkflowOrchestrator):
    async def run(self) -> bool:
        # Assess complexity first
        complexity = await self.assess_complexity()

        # Adjust phases based on complexity
        if complexity == "simple":
            self.phases = [
                MyWorkflowPhase.INITIALIZATION,
                MyWorkflowPhase.TRANSFORMATION,  # Skip analysis
                MyWorkflowPhase.VALIDATION,
            ]
        elif complexity == "complex":
            # Add extra validation phase
            self.phases.append(MyWorkflowPhase.DEEP_VALIDATION)

        return await super().run()
```

### Parallel Phase Execution

Run independent phases in parallel:

```python
import asyncio

async def run_parallel_phases(self, phases: list[MyWorkflowPhase]):
    """Run multiple independent phases concurrently."""
    tasks = [self.executor.run_phase(phase) for phase in phases]
    results = await asyncio.gather(*tasks)

    # Check if all succeeded
    return all(r.success for r in results)
```

### Phase Checkpointing

Resume from last checkpoint:

```python
class CheckpointedOrchestrator(MyWorkflowOrchestrator):
    def __init__(self, *args, checkpoint_file: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.checkpoint_file = checkpoint_file
        self.completed_phases = self._load_checkpoint()

    def _load_checkpoint(self) -> set[str]:
        """Load previously completed phases."""
        if self.checkpoint_file.exists():
            import json
            with open(self.checkpoint_file) as f:
                data = json.load(f)
                return set(data.get("completed_phases", []))
        return set()

    def _save_checkpoint(self, phase: MyWorkflowPhase):
        """Save progress after each phase."""
        import json
        self.completed_phases.add(phase.value)
        with open(self.checkpoint_file, "w") as f:
            json.dump({"completed_phases": list(self.completed_phases)}, f)

    async def run(self) -> bool:
        for phase in self.phases:
            # Skip already completed phases
            if phase.value in self.completed_phases:
                print(f"Skipping completed phase: {phase.value}")
                continue

            result = await self.executor.run_phase(phase)

            if result.success:
                self._save_checkpoint(phase)
            else:
                return False

        return True
```

### Feedback Loops

Implement iterative improvement:

```python
async def run_with_feedback(self, max_iterations: int = 3):
    """Run phases with feedback loop for quality improvement."""

    for iteration in range(max_iterations):
        # Run transformation phase
        transform_result = await self.executor.run_phase(
            MyWorkflowPhase.TRANSFORMATION
        )

        if not transform_result.success:
            return False

        # Run validation phase
        validate_result = await self.executor.run_phase(
            MyWorkflowPhase.VALIDATION
        )

        if validate_result.artifacts.get("approved"):
            print(f"✅ Approved on iteration {iteration + 1}")
            break

        if iteration < max_iterations - 1:
            print(f"⚠️  Not approved, refining... (iteration {iteration + 1})")
            # Loop back to transformation with feedback
            continue
        else:
            print(f"❌ Failed to get approval after {max_iterations} iterations")
            return False

    return True
```

## Best Practices

### 1. Keep Phases Focused

Each phase should have **one clear purpose**:

✅ **Good**: "Gather project context"
❌ **Bad**: "Gather context and write spec and create plan"

### 2. Define Clear Inputs/Outputs

Document what each phase needs and produces:

```python
class PhaseDefinition:
    name: str
    inputs: list[str]  # Files or artifacts from previous phases
    outputs: list[str]  # Files or artifacts this phase produces
    validates: str  # What makes this phase successful
```

### 3. Implement Robust Validation

Validate outputs to catch issues early:

```python
def _validate_output(self, phase, output):
    # 1. Structure validation (required fields present)
    # 2. Type validation (correct data types)
    # 3. Business logic validation (values make sense)
    # 4. Completeness validation (nothing missing)
    pass
```

### 4. Handle Failures Gracefully

Provide clear error messages and recovery options:

```python
if not result.success:
    print(f"Phase {phase} failed: {result.error_message}")
    print(f"Retry count: {result.retry_count}/{MAX_RETRIES}")
    print(f"Artifacts saved to: {result.output_file}")
    # Offer recovery options
```

### 5. Make Phases Resumable

Save progress after each phase to allow resumption:

```python
# Save checkpoint
checkpoint = {
    "completed_phases": [p.value for p in completed],
    "current_phase": current_phase.value,
    "artifacts": artifacts_dict,
    "timestamp": datetime.now().isoformat()
}
```

### 6. Use Descriptive Prompts

Each phase prompt should be self-contained and clear:

```markdown
# Phase Name

## Context
[What has happened before this phase]

## Your Task
[What this phase should accomplish]

## Inputs
[What data/files are available]

## Output Requirements
[Exactly what to produce]

## Validation Criteria
[How output will be validated]
```

## Testing Phase-Based Workflows

### Unit Testing Individual Phases

```python
# tests/test_phases.py
import pytest
from workflows.my_workflow import MyWorkflowExecutor, MyWorkflowPhase

@pytest.mark.asyncio
async def test_initialization_phase():
    executor = MyWorkflowExecutor(
        project_dir=Path("/tmp/test"),
        output_dir=Path("/tmp/output"),
        run_agent_fn=mock_agent_fn
    )

    result = await executor.run_phase(MyWorkflowPhase.INITIALIZATION)

    assert result.success
    assert result.output_file.exists()
    assert "workspace_path" in result.artifacts
```

### Integration Testing Full Workflows

```python
@pytest.mark.asyncio
async def test_full_workflow():
    orchestrator = MyWorkflowOrchestrator(
        project_dir=Path("/tmp/test"),
        output_dir=Path("/tmp/output"),
        run_agent_fn=mock_agent_fn
    )

    success = await orchestrator.run()

    assert success
    artifacts = orchestrator.get_artifacts()
    assert len(artifacts) == 5  # All phases completed
```

### Testing Retry Logic

```python
@pytest.mark.asyncio
async def test_phase_retry():
    # Mock agent that fails twice then succeeds
    call_count = 0

    async def failing_agent_fn(prompt, context):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return False, {}
        return True, {"valid": "output"}

    executor = MyWorkflowExecutor(
        project_dir=Path("/tmp/test"),
        output_dir=Path("/tmp/output"),
        run_agent_fn=failing_agent_fn
    )

    result = await executor.run_phase(MyWorkflowPhase.ANALYSIS)

    assert result.success
    assert result.retry_count == 2
```

## Monitoring and Observability

### Add Logging

```python
import logging

logger = logging.getLogger(__name__)

async def run_phase(self, phase: MyWorkflowPhase):
    logger.info(f"Starting phase: {phase.value}")
    start_time = time.time()

    result = await self.executor.run_phase(phase)

    duration = time.time() - start_time
    logger.info(f"Phase {phase.value} completed in {duration:.2f}s")

    return result
```

### Track Metrics

```python
class MetricsCollector:
    def __init__(self):
        self.metrics = {
            "phase_durations": {},
            "retry_counts": {},
            "success_rates": {}
        }

    def record_phase(self, phase: str, duration: float, success: bool, retries: int):
        self.metrics["phase_durations"][phase] = duration
        self.metrics["retry_counts"][phase] = retries
        self.metrics["success_rates"][phase] = success
```

### Status Updates

Integrate with status line or UI:

```python
async def run_phase(self, phase: MyWorkflowPhase):
    # Update status file for ccstatusline
    self._update_status(f"Running {phase.value}...")

    result = await self.executor.run_phase(phase)

    if result.success:
        self._update_status(f"✅ {phase.value} complete")
    else:
        self._update_status(f"❌ {phase.value} failed")

    return result
```

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Project overview and commands
- [Docker Isolation Proposal](DOCKER_ISOLATION_PROPOSAL.md) - Multi-container pipeline details
- [Isolation Integration Guide](../apps/backend/docs/ISOLATION_INTEGRATION_GUIDE.md) - Code examples

## Summary

The phase-based architecture is a powerful pattern used throughout Auto-Claude:

1. **Spec Creation**: Complexity-adaptive pipeline (3-8 phases)
2. **Implementation**: Subtask-based workflow with feedback loops
3. **Docker Isolation**: Multi-container pipeline with iterative refinement

Key principles:
- ✅ Single responsibility per phase
- ✅ Clear inputs and outputs
- ✅ Validation and retry logic
- ✅ Artifact-based communication
- ✅ Resumability and checkpointing
- ✅ Feedback loops for quality

Apply this pattern to create robust, maintainable workflows that can handle complexity, recover from failures, and provide clear visibility into progress.
