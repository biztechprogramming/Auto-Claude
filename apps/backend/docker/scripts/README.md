# Container Agent Scripts

Production-ready Python scripts that run inside Docker containers to implement the Auto Claude multi-agent orchestration pattern.

## Overview

These scripts enable containerized execution of Auto Claude agents:

- **developer_agent.py** - Implements code based on implementation plans
- **evaluator_agent.py** - Reviews code quality and best practices
- **qa_agent.py** - Runs automated tests and validation

## Architecture

```
Orchestrator (host)
    │
    ├─► developer_agent (container) → Implements features
    │       ↓
    │   commit + push
    │       ↓
    ├─► evaluator_agent (container) → Reviews code
    │       ↓
    │   feedback JSON
    │       ↓
    └─► qa_agent (container) → Runs tests
            ↓
        feedback JSON
```

## Scripts

### developer_agent.py

Clones repository, implements code using Claude SDK, commits and pushes changes.

**Environment Variables:**
- `REPO_URL` (required) - Git repository URL
- `BASE_BRANCH` (required) - Base branch (e.g., main, develop)
- `BRANCH_NAME` (required) - Feature branch to create/checkout
- `IMPLEMENTATION_PLAN` (required) - JSON string with implementation plan
- `FEEDBACK_COMMENTS` (optional) - JSON string with feedback from previous iteration
- `CLAUDE_CODE_OAUTH_TOKEN` (required) - OAuth token for Claude SDK
- `MODEL` (optional) - Claude model (default: claude-3-7-sonnet-20250219)
- `MAX_TURNS` (optional) - Max conversation turns (default: 100)

**Output:**
```
COMMIT_SHA=abc123def456
```

**Exit Codes:**
- 0 = Success
- 1 = Failure

**Example:**
```bash
docker run -e REPO_URL=https://github.com/org/repo \
           -e BASE_BRANCH=main \
           -e BRANCH_NAME=feature/new-feature \
           -e IMPLEMENTATION_PLAN='{"phases":[...]}' \
           -e CLAUDE_CODE_OAUTH_TOKEN=$TOKEN \
           developer-agent
```

### evaluator_agent.py

Clones repository, reviews code quality using Claude SDK, outputs structured feedback.

**Environment Variables:**
- `REPO_URL` (required) - Git repository URL
- `BRANCH_NAME` (required) - Branch to evaluate
- `BASE_BRANCH` (optional) - Base branch to compare against (default: main)
- `CLAUDE_CODE_OAUTH_TOKEN` (required) - OAuth token for Claude SDK
- `MODEL` (optional) - Claude model (default: claude-3-7-sonnet-20250219)
- `MAX_TURNS` (optional) - Max conversation turns (default: 50)

**Output:**
```json
FEEDBACK_JSON={"approved": true, "comments": [{"message": "...", "file_path": "...", "line_number": 42, "severity": "warning"}]}
```

**Exit Codes:**
- 0 = Always (approval status in JSON)

**Example:**
```bash
docker run -e REPO_URL=https://github.com/org/repo \
           -e BRANCH_NAME=feature/new-feature \
           -e CLAUDE_CODE_OAUTH_TOKEN=$TOKEN \
           evaluator-agent
```

### qa_agent.py

Clones repository, runs tests (auto-detected or custom), outputs test results.

**Environment Variables:**
- `REPO_URL` (required) - Git repository URL
- `BRANCH_NAME` (required) - Branch to test
- `TEST_COMMAND` (optional) - Custom test command (auto-detected if not set)
- `PLAYWRIGHT_ENABLED` (optional) - Set to 'true' to run Playwright tests (default: false)
- `CLAUDE_CODE_OAUTH_TOKEN` (optional) - OAuth token for intelligent test analysis

**Test Framework Detection:**
- Node.js: `npm test` (from package.json)
- Python: `pytest` (if pytest.ini or pytest in requirements.txt)
- Go: `go test ./...`
- Rust: `cargo test`

**Output:**
```json
FEEDBACK_JSON={"passed": true, "comments": [{"message": "Test failed: ...", "file_path": "test/example.test.js", "severity": "error"}]}
```

**Exit Codes:**
- 0 = Always (pass/fail status in JSON)

**Example:**
```bash
docker run -e REPO_URL=https://github.com/org/repo \
           -e BRANCH_NAME=feature/new-feature \
           -e PLAYWRIGHT_ENABLED=true \
           qa-agent
```

## Docker Integration

These scripts are designed to run in containers built from the Dockerfiles in `/apps/backend/docker/`:

- `Dockerfile.developer` - Developer agent image
- `Dockerfile.evaluator` - Evaluator agent image
- `Dockerfile.qa` - QA agent image
- `Dockerfile.base` - Shared base image

### Volume Mounts

Scripts expect prompts to be mounted at `/app/prompts`:

```bash
docker run -v $(pwd)/apps/backend/prompts:/app/prompts \
           -e REPO_URL=... \
           developer-agent
```

## Security

All scripts implement defense-in-depth security:

1. **Sandbox** - OS-level bash command isolation
2. **Permissions** - File operations restricted to repository directory
3. **Command Allowlist** - Bash commands validated against allowlist
4. **Tool Filtering** - Only necessary tools enabled per agent

## Error Handling

All scripts:
- Log to stderr (structured logging)
- Output results to stdout (machine-readable)
- Always exit 0 (except developer_agent on critical failure)
- Include comprehensive error context in output JSON

## Development

### Testing Locally

```bash
# Set environment variables
export REPO_URL=https://github.com/your/repo
export BRANCH_NAME=test-branch
export BASE_BRANCH=main
export CLAUDE_CODE_OAUTH_TOKEN=$(cat ~/.claude/oauth_token)

# Run developer agent
python developer_agent.py

# Run evaluator agent
python evaluator_agent.py

# Run QA agent
python qa_agent.py
```

### Adding New Features

1. Update the relevant script
2. Update environment variable documentation
3. Update output format if changed
4. Add error handling for new edge cases
5. Test with real repository

## Orchestration Example

```python
# Example orchestration pattern
import subprocess
import json

# 1. Run developer agent
result = subprocess.run(
    ["docker", "run", "-e", "REPO_URL=...", "developer-agent"],
    capture_output=True,
    text=True,
)
commit_sha = result.stdout.split("=")[1].strip()

# 2. Run evaluator agent
result = subprocess.run(
    ["docker", "run", "-e", "REPO_URL=...", "evaluator-agent"],
    capture_output=True,
    text=True,
)
feedback_json = result.stdout.split("=", 1)[1].strip()
feedback = json.loads(feedback_json)

# 3. If approved, run QA agent
if feedback["approved"]:
    result = subprocess.run(
        ["docker", "run", "-e", "REPO_URL=...", "qa-agent"],
        capture_output=True,
        text=True,
    )
    qa_json = result.stdout.split("=", 1)[1].strip()
    qa_result = json.loads(qa_json)

    if qa_result["passed"]:
        print("All checks passed! Ready to merge.")
```

## Troubleshooting

### "Failed to import Claude SDK"
- Ensure `claude-agent-sdk` is installed in container
- Check Dockerfile includes SDK installation

### "CLAUDE_CODE_OAUTH_TOKEN not set"
- Run `claude setup-token` on host
- Pass token via environment variable

### "Repository clone failed"
- Check `REPO_URL` is accessible
- Verify git credentials if private repository
- Check network connectivity from container

### "Test framework not detected"
- Set `TEST_COMMAND` explicitly
- Ensure test configuration files exist (package.json, pytest.ini, etc.)

### "No JSON in output"
- Check stderr logs for errors
- Verify Claude SDK response format
- Review agent prompt configuration

## Future Enhancements

- [ ] Parallel subtask execution in developer_agent
- [ ] Incremental test runs (only affected tests)
- [ ] Performance benchmarking integration
- [ ] Security scanning (SAST/DAST)
- [ ] Dependency vulnerability checks
- [ ] Code coverage analysis
- [ ] Custom hook system for pre/post actions
