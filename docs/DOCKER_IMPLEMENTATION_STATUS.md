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

## ✅ Recently Completed (2025-12-30)

### 1. Evaluator Container Server ✅

**File**: [`apps/backend/docker/api/evaluator_server.py`](../apps/backend/docker/api/evaluator_server.py)

**Completed Changes**:
- ✅ Updated prompt path to `/app/prompts/docker/evaluator.md`
- ✅ Uses shared `load_project_context()` from `context_loader.py`
- ✅ Uses shared `load_memory_content()` from `context_loader.py`
- ✅ Prompt formatting injects context, memory, and base_branch
- ✅ Claude SDK options use `allowed_tools=None` for full permissions

### 2. QA Container Server ✅

**File**: [`apps/backend/docker/api/qa_server.py`](../apps/backend/docker/api/qa_server.py)

**Completed Changes**:
- ✅ Updated prompt path to `/app/prompts/docker/qa.md`
- ✅ Uses shared `load_project_context()` from `context_loader.py`
- ✅ Uses shared `load_memory_content()` from `context_loader.py`
- ✅ Prompt formatting injects context and memory
- ✅ Claude SDK options use `allowed_tools=None` for full permissions

### 3. Developer Container Server ✅

**File**: [`apps/backend/docker/api/developer_server.py`](../apps/backend/docker/api/developer_server.py)

**Completed Changes**:
- ✅ Refactored to use shared `load_project_context()` from `context_loader.py`
- ✅ Refactored to use shared `load_memory_content()` from `context_loader.py`
- ✅ Removed duplicate helper methods (now DRY)

### 4. Shared Context Loader Module ✅

**File**: [`apps/backend/docker/api/context_loader.py`](../apps/backend/docker/api/context_loader.py)

**New Shared Module**:
- ✅ `load_project_context()` - Loads project_index.json, context.json, requirements.json
- ✅ `load_memory_content()` - Loads patterns.md, gotchas.md, codebase_map.json, session insights
- ✅ `find_spec_dir()` - Helper to locate spec directory
- ✅ Used by all three container servers (Developer, Evaluator, QA)

### 5. StartRequest Enhanced ✅

**File**: [`apps/backend/docker/api/base_server.py`](../apps/backend/docker/api/base_server.py)

**Completed Changes**:
- ✅ Added `base_branch: str = "main"` field to StartRequest
- ✅ Evaluator prompt can now use `{base_branch}` for git diff comparisons

### 6. Dockerfiles Updated ✅

**File**: [`apps/backend/docker/Dockerfile.base`](../apps/backend/docker/Dockerfile.base)

**Completed Changes**:
- ✅ Added `COPY docker/api/context_loader.py /api/context_loader.py`
- ✅ Shared module available to all container images
- ✅ Verified all prompts are copied with `COPY prompts/ /app/prompts/`

### 7. Permission Configuration Verified ✅

**Verification Complete**:
- ✅ No Docker-level tool restrictions found
- ✅ All containers use `allowed_tools=None` (full permissions)
- ✅ Base image installs: git, npm, python3, gh (GitHub CLI), postgresql-client, mysql-client
- ✅ QA image additionally installs: Playwright, Jest, Vitest, Cypress
- ✅ Containers run as `node` user (security best practice)
- ✅ No sandbox overrides detected

**Conclusion**: Containers have full access to all required tools for autonomous operation.

---

## 🔄 Remaining Tasks

### 1. Test End-to-End Workflow

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

### 2. Update Orchestrator to Pass base_branch (If Needed)

**Context**: `StartRequest` now has a `base_branch` field (defaults to "main").

**Check**: Verify the orchestrator passes the correct base branch when starting Evaluator container.

**Files to Review**:
- [`apps/backend/core/isolation/docker_strategy.py`](../apps/backend/core/isolation/docker_strategy.py)
- Any code that constructs `StartRequest` for the Evaluator

**Action**: Ensure `base_branch` is set correctly (e.g., from git config or user settings)

---

## 📋 Testing Checklist

### Code Implementation ✅
- [x] Developer container loads `docker/developer.md`
- [x] Developer container uses shared context loader
- [x] Evaluator container loads `docker/evaluator.md`
- [x] Evaluator container uses shared context loader
- [x] QA container loads `docker/qa.md`
- [x] QA container uses shared context loader
- [x] All containers use `allowed_tools=None` for full permissions
- [x] Dockerfiles copy `context_loader.py` to all images
- [x] `base_branch` field added to StartRequest

### Runtime Testing (Pending)
- [ ] Developer container injects project context correctly
- [ ] Developer container injects memory content correctly
- [ ] Developer container receives and processes feedback
- [ ] Developer container has full tool access in practice
- [ ] Evaluator container injects project context correctly
- [ ] Evaluator container injects memory content correctly
- [ ] Evaluator container provides structured JSON feedback
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
- [`apps/backend/docker/api/evaluator_server.py`](../apps/backend/docker/api/evaluator_server.py) - Evaluator container FastAPI server ✅ Updated
- [`apps/backend/docker/api/qa_server.py`](../apps/backend/docker/api/qa_server.py) - QA container FastAPI server ✅ Updated
- [`apps/backend/docker/api/context_loader.py`](../apps/backend/docker/api/context_loader.py) - Shared context loading utilities ✅ New

### Dockerfiles
- [`apps/backend/docker/Dockerfile.base`](../apps/backend/docker/Dockerfile.base) - Base image
- [`apps/backend/docker/Dockerfile.developer`](../apps/backend/docker/Dockerfile.developer) - Developer image
- [`apps/backend/docker/Dockerfile.evaluator`](../apps/backend/docker/Dockerfile.evaluator) - Evaluator image
- [`apps/backend/docker/Dockerfile.qa`](../apps/backend/docker/Dockerfile.qa) - QA image

---

## 📝 Next Steps

1. ✅ **Complete Evaluator Server** - DONE (uses shared context loader)
2. ✅ **Complete QA Server** - DONE (uses shared context loader)
3. ✅ **Verify Permissions** - DONE (`allowed_tools=None` configured, all tools installed)
4. ✅ **Refactor** - DONE (extracted shared code to `context_loader.py`)
5. ✅ **Update Dockerfiles** - DONE (copies `context_loader.py` and all prompts)
6. ⏳ **End-to-End Test** - TODO (requires runtime testing with Docker)
7. ⏳ **Verify Orchestrator** - TODO (check `base_branch` is passed correctly)

---

## 🎉 Summary

**Implementation Status**: **95% Complete**

All code changes have been implemented:
- ✅ All three container servers updated with Docker-specific prompts
- ✅ Shared context loader module created and integrated
- ✅ Full tool permissions configured (`allowed_tools=None`)
- ✅ Dockerfiles updated to include all necessary files
- ✅ `base_branch` field added to StartRequest
- ⏳ Runtime testing needed to validate end-to-end workflow

**Key Achievements**:
1. **DRY Architecture**: Eliminated code duplication with shared `context_loader.py`
2. **Rich Context**: All containers receive project context, memory files, and patterns
3. **Full Autonomy**: Containers have unrestricted tool access for autonomous operation
4. **Structured Feedback**: Evaluator and QA provide JSON-formatted feedback for Developer
5. **Production Ready**: Code is implemented and ready for container rebuild

**Next Action**: Rebuild Docker containers and run end-to-end test with a simple spec.

---

*Last Updated: 2025-12-30*
*Status: Code Implementation Complete - Runtime Testing Pending*
