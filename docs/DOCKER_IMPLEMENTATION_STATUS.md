# Docker Container Implementation Status

## Overview

This document tracks the implementation of configurable phases, improved prompts, and memory integration for the Docker-based multi-container workflow in Auto-Claude.

**Goal**: Enhance Docker containers with phase-based architecture, container-specific prompts that include memory/spec data, and full permissions for autonomous operation.

---

## ✅ Completed Work

### 1. Container-Specific Prompts Created

Created three comprehensive, Docker-specific prompts in [`apps/backend/prompts/docker/`](../apps/backend/prompts/docker/):

#### [`developer.md`](../apps/backend/prompts/docker/developer.md)
**Purpose**: Guide the Developer container through autonomous implementation.

**Key Features**:
- **Full Permissions Acknowledgment**: Explicitly states full filesystem access in Docker container
- **Template Variables**: Placeholders for dynamic content injection:
  - `{branch_name}` - Git feature branch name
  - `{spec_content}` - Full specification document
  - `{project_context}` - Project structure and configuration
  - `{memory_content}` - Patterns, gotchas, session insights
  - `{feedback_comments}` - Feedback from Evaluator/QA (JSON format)
- **Phase-Based Workflow**:
  1. Setup and Discovery - Clone, install, start services
  2. Implementation - Follow patterns, write code, write tests
  3. Verification - Run tests, manual checks
  4. Commit and Push - Git workflow
- **Feedback Handling**: Clear instructions for addressing Evaluator/QA feedback with severity prioritization
- **Context7 Integration**: Instructions for looking up third-party library documentation
- **Best Practices**: Security, performance, code organization, git hygiene
- **Success Criteria**: Checklist before marking work complete

#### [`evaluator.md`](../apps/backend/prompts/docker/evaluator.md)
**Purpose**: Guide the Evaluator container through code quality review.

**Key Features**:
- **Completeness Checking**: Verify all spec requirements are implemented
- **Code Quality Review**:
  - Pattern adherence (using `memory/patterns.md`)
  - Code structure and cleanliness
  - Security vulnerabilities (XSS, SQL injection, command injection, secrets)
  - Performance issues (N+1 queries, inefficient algorithms)
  - Testing coverage and quality
  - Error handling completeness
- **Third-Party Library Validation**: Use Context7 to verify correct API usage
- **JSON Feedback Format**: Structured output for Developer to consume:
  ```json
  {
    "approved": true/false,
    "summary": "...",
    "issues": [
      {
        "severity": "critical|major|minor",
        "category": "completeness|security|quality|testing|library_usage|performance",
        "message": "...",
        "file_path": "...",
        "line_number": 42,
        "suggested_fix": "...",
        "context7_reference": "..."
      }
    ]
  }
  ```
- **Decision Workflow**: Clear APPROVE/REJECT criteria

#### [`qa.md`](../apps/backend/prompts/docker/qa.md)
**Purpose**: Guide the QA container through comprehensive functional testing.

**Key Features**:
- **Automated Test Execution**:
  - Unit tests
  - Integration tests
  - End-to-end tests
- **Manual Functional Testing**:
  - Browser automation (Puppeteer/Playwright for web, Electron tools for desktop)
  - API testing (curl-based endpoint validation)
  - Console error detection (CRITICAL requirement)
- **Acceptance Criteria Validation**: Systematic check of every criterion from spec
- **Regression Testing**: Verify existing features still work
- **Edge Case Testing**: Boundary conditions, error handling
- **JSON Results Format**: Structured PASS/FAIL with detailed issue reports
- **Decision Criteria**: Clear PASS/FAIL rules

### 2. Workflow Configuration Updated

**File**: [`apps/backend/core/isolation/workflow_config.py`](../apps/backend/core/isolation/workflow_config.py)

**Changes**:
- Line 58: Developer uses `docker/developer.md` (was `coder.md`)
- Line 70: Evaluator uses `docker/evaluator.md` (was `qa_reviewer.md`)
- Line 82: QA uses `docker/qa.md` (was `qa_reviewer.md`)

### 3. Developer Container Enhanced

**File**: [`apps/backend/docker/api/developer_server.py`](../apps/backend/docker/api/developer_server.py)

**Changes**:

#### Prompt Loading (Lines 95-115)
```python
# Load Docker-specific developer prompt
developer_prompt_file = Path("/app/prompts/docker/developer.md")
developer_prompt = developer_prompt_file.read_text(encoding="utf-8")

# Load additional context files
project_context = self._load_project_context(repo_dir)
memory_content = self._load_memory_content(repo_dir)

# Replace placeholders in the prompt template
full_prompt = developer_prompt.format(
    branch_name=request.branch_name,
    spec_content=request.spec_content,
    project_context=project_context,
    memory_content=memory_content,
    feedback_comments=request.feedback_comments or "No feedback from previous iterations."
)
```

#### Project Context Loader (Lines 196-241)
**Method**: `_load_project_context(repo_dir: Path) -> str`

Loads from `.auto-claude/specs/{spec-name}/`:
- `project_index.json` - Project structure, services, ports, commands
- `context.json` - Relevant codebase context, files to reference
- `requirements.json` - User requirements, acceptance criteria

Returns formatted markdown with JSON code blocks.

#### Memory Content Loader (Lines 243-305)
**Method**: `_load_memory_content(repo_dir: Path) -> str`

Loads from `.auto-claude/specs/{spec-name}/memory/`:
- `patterns.md` - Established code patterns to follow
- `gotchas.md` - Known pitfalls to avoid
- `codebase_map.json` - File purpose documentation
- `session_insights/session_*.json` - Last 3 session learnings

Returns formatted markdown combining all memory sources.

#### Claude SDK Options (Lines 147-153)
```python
async for message in query(
    prompt=full_prompt,
    options=ClaudeAgentOptions(
        allowed_tools=None,  # None = all tools allowed
        cwd=str(repo_dir),   # Set working directory to the repository
    )
):
```

**Note**: `allowed_tools=None` grants full permissions - all Claude SDK tools are available.

---

## 🔄 In Progress / Not Yet Done

### 1. Update Evaluator Container Server

**File**: [`apps/backend/docker/api/evaluator_server.py`](../apps/backend/docker/api/evaluator_server.py)

**Required Changes**:
- Update prompt path from `/app/prompts/qa_reviewer.md` to `/app/prompts/docker/evaluator.md`
- Add `_load_project_context()` method (same as developer)
- Add `_load_memory_content()` method (same as developer)
- Update prompt formatting to inject context and memory
- Ensure Claude SDK options use `allowed_tools=None`

**Template**:
```python
async def _execute_with_claude_sdk(self, request: StartRequest, repo_dir: Path):
    # Load Docker-specific evaluator prompt
    evaluator_prompt_file = Path("/app/prompts/docker/evaluator.md")
    evaluator_prompt = evaluator_prompt_file.read_text(encoding="utf-8")

    # Load context and memory
    project_context = self._load_project_context(repo_dir)
    memory_content = self._load_memory_content(repo_dir)

    # Format prompt
    full_prompt = evaluator_prompt.format(
        branch_name=request.branch_name,
        base_branch=request.base_branch,  # May need to add this to StartRequest
        spec_content=request.spec_content,
        project_context=project_context,
        memory_content=memory_content
    )

    # Run with full permissions
    async for message in query(
        prompt=full_prompt,
        options=ClaudeAgentOptions(
            allowed_tools=None,
            cwd=str(repo_dir),
        )
    ):
        # Handle messages...
```

### 2. Update QA Container Server

**File**: [`apps/backend/docker/api/qa_server.py`](../apps/backend/docker/api/qa_server.py)

**Required Changes**:
- Update prompt path from `/app/prompts/qa_reviewer.md` to `/app/prompts/docker/qa.md`
- Add `_load_project_context()` method (same as developer)
- Add `_load_memory_content()` method (same as developer)
- Update prompt formatting to inject context and memory
- Ensure Claude SDK options use `allowed_tools=None`

**Template**: Same structure as Evaluator above.

### 3. Verify Permission Configuration

**Context**: All three containers currently use `allowed_tools=None` which should allow all tools. However, we need to verify:

**Check**:
1. Are there any Docker-level restrictions in the Dockerfiles?
2. Are there sandbox settings that might override `allowed_tools=None`?
3. Do containers have access to all required tools (git, npm, python, etc.)?

**Files to Review**:
- [`apps/backend/docker/Dockerfile.base`](../apps/backend/docker/Dockerfile.base)
- [`apps/backend/docker/Dockerfile.developer`](../apps/backend/docker/Dockerfile.developer)
- [`apps/backend/docker/Dockerfile.evaluator`](../apps/backend/docker/Dockerfile.evaluator)
- [`apps/backend/docker/Dockerfile.qa`](../apps/backend/docker/Dockerfile.qa)

### 4. Add Base Branch to StartRequest (If Needed)

**Context**: The Evaluator prompt template uses `{base_branch}` placeholder, but `StartRequest` may not include it.

**Check**: [`apps/backend/docker/api/base_server.py`](../apps/backend/docker/api/base_server.py)
- Does `StartRequest` have `base_branch` field?
- If not, add it
- Ensure orchestrator passes it when starting Evaluator

### 5. Test End-to-End Workflow

**Test Scenario**:
1. Create a simple spec
2. Run Docker isolation mode
3. Verify Developer container:
   - Loads `docker/developer.md`
   - Injects memory and context
   - Has full tool permissions
   - Implements the spec
   - Commits and pushes
4. Verify Evaluator container:
   - Loads `docker/evaluator.md`
   - Reviews code quality
   - Provides structured feedback (if issues found)
5. Verify QA container:
   - Loads `docker/qa.md`
   - Runs automated tests
   - Performs manual testing
   - Provides structured results

**Success Criteria**:
- All prompts load without errors
- Memory/context properly injected
- Containers can access all tools
- Feedback loops work (Developer receives and addresses feedback)
- Final output is production-ready code

### 6. Extract Helper Methods to Shared Module (Optional Refactor)

**Context**: `_load_project_context()` and `_load_memory_content()` are identical across all three containers.

**Improvement**: Move to shared module to reduce duplication.

**Implementation**:
1. Create [`apps/backend/docker/api/context_loader.py`](../apps/backend/docker/api/context_loader.py)
2. Move both methods there
3. Import in all three servers
4. Update method calls

**Benefits**:
- DRY (Don't Repeat Yourself)
- Easier to maintain
- Consistent behavior across containers

---

## 📋 Testing Checklist

Before marking this feature complete, test:

- [ ] Developer container loads `docker/developer.md`
- [ ] Developer container injects project context correctly
- [ ] Developer container injects memory content correctly
- [ ] Developer container receives and processes feedback
- [ ] Developer container has full tool access (`allowed_tools=None` works)
- [ ] Evaluator container loads `docker/evaluator.md`
- [ ] Evaluator container injects project context correctly
- [ ] Evaluator container injects memory content correctly
- [ ] Evaluator container provides structured JSON feedback
- [ ] QA container loads `docker/qa.md`
- [ ] QA container injects project context correctly
- [ ] QA container injects memory content correctly
- [ ] QA container provides structured JSON results
- [ ] Feedback loop works: Evaluator → Developer → Evaluator
- [ ] Feedback loop works: QA → Developer → QA
- [ ] Max iterations respected (3 by default)
- [ ] All containers can commit and push to Git
- [ ] Memory files are preserved between iterations
- [ ] Console errors are detected and reported by QA

---

## 🏗️ Architecture Summary

### Data Flow

```
Orchestrator (Host)
    │
    ├─> Developer Container
    │   ├─ Load docker/developer.md
    │   ├─ Load project_context (project_index, context, requirements)
    │   ├─ Load memory_content (patterns, gotchas, codebase_map, insights)
    │   ├─ Format prompt with placeholders
    │   ├─ Run Claude SDK (allowed_tools=None)
    │   ├─ Implement spec
    │   ├─ Commit changes
    │   └─ Push to feature branch
    │
    ├─> Evaluator Container
    │   ├─ Load docker/evaluator.md
    │   ├─ Load project_context
    │   ├─ Load memory_content
    │   ├─ Format prompt with placeholders
    │   ├─ Run Claude SDK (allowed_tools=None)
    │   ├─ Review code quality
    │   └─ Return JSON feedback (APPROVE/REJECT)
    │
    └─> QA Container
        ├─ Load docker/qa.md
        ├─ Load project_context
        ├─ Load memory_content
        ├─ Format prompt with placeholders
        ├─ Run Claude SDK (allowed_tools=None)
        ├─ Run automated tests
        ├─ Perform manual testing
        └─ Return JSON results (PASS/FAIL)
```

### Feedback Loop Flow

```
Developer Implements
    ↓
Evaluator Reviews
    ↓
Issues Found? ──YES──> Developer Fixes (iteration++)
    ↓ NO                      ↓
QA Tests                      ↓
    ↓                    (loop back to Evaluator)
Issues Found? ──YES──> Developer Fixes (iteration++)
    ↓ NO
APPROVED (Ready for merge)
```

**Max Iterations**: 3 (configurable via `MAX_FEEDBACK_ITERATIONS`)

---

## 📚 Related Documentation

- [Phase-Based Architecture Guide](PHASE_BASED_ARCHITECTURE.md) - Overview of phase-based workflow pattern
- [Docker Isolation Proposal](DOCKER_ISOLATION_PROPOSAL.md) - Original multi-container pipeline design
- [Isolation Integration Guide](../apps/backend/docs/ISOLATION_INTEGRATION_GUIDE.md) - Code examples for isolation strategies
- [CLAUDE.md](../CLAUDE.md) - Project overview and commands

---

## 🔗 Key Files

### Prompts
- [`apps/backend/prompts/docker/developer.md`](../apps/backend/prompts/docker/developer.md) - Developer container prompt
- [`apps/backend/prompts/docker/evaluator.md`](../apps/backend/prompts/docker/evaluator.md) - Evaluator container prompt
- [`apps/backend/prompts/docker/qa.md`](../apps/backend/prompts/docker/qa.md) - QA container prompt

### Configuration
- [`apps/backend/core/isolation/workflow_config.py`](../apps/backend/core/isolation/workflow_config.py) - Workflow step definitions
- [`apps/backend/core/isolation/docker_strategy.py`](../apps/backend/core/isolation/docker_strategy.py) - Docker isolation implementation

### Container Servers
- [`apps/backend/docker/api/developer_server.py`](../apps/backend/docker/api/developer_server.py) - Developer container FastAPI server ✅ Updated
- [`apps/backend/docker/api/evaluator_server.py`](../apps/backend/docker/api/evaluator_server.py) - Evaluator container FastAPI server ⏳ TODO
- [`apps/backend/docker/api/qa_server.py`](../apps/backend/docker/api/qa_server.py) - QA container FastAPI server ⏳ TODO

### Dockerfiles
- [`apps/backend/docker/Dockerfile.base`](../apps/backend/docker/Dockerfile.base) - Base image
- [`apps/backend/docker/Dockerfile.developer`](../apps/backend/docker/Dockerfile.developer) - Developer image
- [`apps/backend/docker/Dockerfile.evaluator`](../apps/backend/docker/Dockerfile.evaluator) - Evaluator image
- [`apps/backend/docker/Dockerfile.qa`](../apps/backend/docker/Dockerfile.qa) - QA image

---

## 📝 Next Steps

1. **Complete Evaluator Server** - Apply the same pattern as Developer
2. **Complete QA Server** - Apply the same pattern as Developer
3. **Verify Permissions** - Ensure `allowed_tools=None` works in Docker
4. **End-to-End Test** - Run a complete workflow with all three containers
5. **Refactor (Optional)** - Extract shared code to common module
6. **Update Documentation** - Document the new prompt template format
7. **Update Dockerfiles** - Ensure new prompt files are copied into images

---

*Last Updated: 2025-12-30*
*Status: Developer Container Complete, Evaluator and QA Pending*
