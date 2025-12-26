# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Auto Claude is a multi-agent autonomous coding framework that builds software through coordinated AI agent sessions. It uses the Claude Agent SDK to run agents in isolated workspaces with security controls.

**CRITICAL: All AI interactions use the Claude Agent SDK (`claude-agent-sdk` package), NOT the Anthropic API directly.**

## Project Structure

```
autonomous-coding/
├── apps/
│   ├── backend/           # Python backend/CLI - ALL agent logic lives here
│   │   ├── core/          # Client, auth, security
│   │   ├── agents/        # Agent implementations
│   │   ├── spec_agents/   # Spec creation agents
│   │   ├── integrations/  # Graphiti, Linear, GitHub
│   │   └── prompts/       # Agent system prompts
│   └── frontend/          # Electron desktop UI
├── guides/                # Documentation
├── tests/                 # Test suite
└── scripts/               # Build and utility scripts
```

**When working with AI/LLM code:**
- Look in `apps/backend/core/client.py` for the Claude SDK client setup
- Reference `apps/backend/agents/` for working agent implementations
- Check `apps/backend/spec_agents/` for spec creation agent examples
- NEVER use `anthropic.Anthropic()` directly - always use `create_client()` from `core.client`

**Frontend (Electron Desktop App):**
- Built with Electron, React, TypeScript
- AI agents can perform E2E testing using the Electron MCP server
- When bug fixing or implementing features, use the Electron MCP server for automated testing
- See "End-to-End Testing" section below for details

## Commands

### Setup

**Requirements:**
- Python 3.12+ (required for backend)
- Node.js (for frontend)

```bash
# Install all dependencies from root
npm run install:all

# Or install separately:
# Backend (from apps/backend/)
cd apps/backend && uv venv && uv pip install -r requirements.txt

# Frontend (from apps/frontend/)
cd apps/frontend && npm install

# Set up OAuth token
claude setup-token
# Add to apps/backend/.env: CLAUDE_CODE_OAUTH_TOKEN=your-token
```

### Creating and Running Specs
```bash
cd apps/backend

# Create a spec interactively
python spec_runner.py --interactive

# Create spec from task description
python spec_runner.py --task "Add user authentication"

# Force complexity level (simple/standard/complex)
python spec_runner.py --task "Fix button" --complexity simple

# Run autonomous build
python run.py --spec 001

# List all specs
python run.py --list
```

### Workspace Management
```bash
cd apps/backend

# Review changes in isolated worktree
python run.py --spec 001 --review

# Merge completed build into project
python run.py --spec 001 --merge

# Discard build
python run.py --spec 001 --discard
```

### QA Validation
```bash
cd apps/backend

# Run QA manually
python run.py --spec 001 --qa

# Check QA status
python run.py --spec 001 --qa-status
```

### Testing
```bash
# Install test dependencies (required first time)
cd apps/backend && uv pip install -r ../../tests/requirements-test.txt

# Run all tests (use virtual environment pytest)
apps/backend/.venv/bin/pytest tests/ -v

# Run single test file
apps/backend/.venv/bin/pytest tests/test_security.py -v

# Run specific test
apps/backend/.venv/bin/pytest tests/test_security.py::test_bash_command_validation -v

# Skip slow tests
apps/backend/.venv/bin/pytest tests/ -m "not slow"

# Or from root
npm run test:backend
```

### Spec Validation
```bash
python apps/backend/validate_spec.py --spec-dir apps/backend/specs/001-feature --checkpoint all
```

### Releases
```bash
# 1. Bump version on your branch (creates commit, no tag)
node scripts/bump-version.js patch   # 2.8.0 -> 2.8.1
node scripts/bump-version.js minor   # 2.8.0 -> 2.9.0
node scripts/bump-version.js major   # 2.8.0 -> 3.0.0

# 2. Push and create PR to main
git push origin your-branch
gh pr create --base main

# 3. Merge PR → GitHub Actions automatically:
#    - Creates tag
#    - Builds all platforms
#    - Creates release with changelog
#    - Updates README
```

See [RELEASE.md](RELEASE.md) for detailed release process documentation.

## Architecture

### Core Pipeline

**Spec Creation (spec_runner.py)** - Dynamic 3-8 phase pipeline based on task complexity:
- SIMPLE (3 phases): Discovery → Quick Spec → Validate
- STANDARD (6-7 phases): Discovery → Requirements → [Research] → Context → Spec → Plan → Validate
- COMPLEX (8 phases): Full pipeline with Research and Self-Critique phases

**Implementation (run.py → agent.py)** - Multi-session build:
1. Planner Agent creates subtask-based implementation plan
2. Coder Agent implements subtasks (can spawn subagents for parallel work)
3. QA Reviewer validates acceptance criteria (can perform E2E testing via Electron MCP for frontend changes)
4. QA Fixer resolves issues in a loop (with E2E testing to verify fixes)

### Key Components (apps/backend/)

**Core Infrastructure:**
- **core/client.py** - Claude Agent SDK client factory with security hooks and tool permissions
- **core/security.py** - Dynamic command allowlisting based on detected project stack
- **core/auth.py** - OAuth token management for Claude SDK authentication
- **agents/** - Agent implementations (planner, coder, qa_reviewer, qa_fixer)
- **spec_agents/** - Spec creation agents (gatherer, researcher, writer, critic)

**Memory & Context:**
- **integrations/graphiti/** - Graphiti memory system (mandatory)
  - `queries_pkg/graphiti.py` - Main GraphitiMemory class
  - `queries_pkg/client.py` - LadybugDB client wrapper
  - `queries_pkg/queries.py` - Graph query operations
  - `queries_pkg/search.py` - Semantic search logic
  - `queries_pkg/schema.py` - Graph schema definitions
- **graphiti_config.py** - Configuration and validation for Graphiti integration
- **graphiti_providers.py** - Multi-provider factory (OpenAI, Anthropic, Azure, Ollama, Google AI)
- **agents/memory_manager.py** - Session memory orchestration

**Workspace & Security:**
- **cli/worktree.py** - Git worktree isolation for safe feature development
- **context/project_analyzer.py** - Project stack detection for dynamic tooling
- **auto_claude_tools.py** - Custom MCP tools integration

**Integrations:**
- **linear_updater.py** - Optional Linear integration for progress tracking
- **runners/github/** - GitHub Issues & PRs automation
- **Electron MCP** - E2E testing integration for QA agents (Chrome DevTools Protocol)
  - Enabled with `ELECTRON_MCP_ENABLED=true` in `.env`
  - Allows QA agents to interact with running Electron app
  - See "End-to-End Testing" section for details

### Agent Prompts (apps/backend/prompts/)

| Prompt | Purpose |
|--------|---------|
| planner.md | Creates implementation plan with subtasks |
| coder.md | Implements individual subtasks |
| coder_recovery.md | Recovers from stuck/failed subtasks |
| qa_reviewer.md | Validates acceptance criteria |
| qa_fixer.md | Fixes QA-reported issues |
| spec_gatherer.md | Collects user requirements |
| spec_researcher.md | Validates external integrations |
| spec_writer.md | Creates spec.md document |
| spec_critic.md | Self-critique using ultrathink |
| complexity_assessor.md | AI-based complexity assessment |

### Spec Directory Structure

Each spec in `.auto-claude/specs/XXX-name/` contains:
- `spec.md` - Feature specification
- `requirements.json` - Structured user requirements
- `context.json` - Discovered codebase context
- `implementation_plan.json` - Subtask-based plan with status tracking
- `qa_report.md` - QA validation results
- `QA_FIX_REQUEST.md` - Issues to fix (when rejected)

### Isolation Strategy

Auto Claude supports two isolation methods for safe, isolated builds:

#### Worktree Mode (Default)

Uses git worktrees for isolated builds. All branches stay LOCAL until user explicitly pushes:

```
main (user's branch)
└── auto-claude/{spec-name}  ← spec branch (isolated worktree)
```

**Key principles:**
- ONE branch per spec (`auto-claude/{spec-name}`)
- Parallel work uses subagents (agent decides when to spawn)
- NO automatic pushes to GitHub - user controls when to push
- User reviews in spec worktree (`.worktrees/{spec-name}/`)
- Final merge: spec branch → main (after user approval)

**Workflow:**
1. Build runs in isolated worktree on spec branch
2. Agent implements subtasks (can spawn subagents for parallel work)
3. User tests feature in `.worktrees/{spec-name}/`
4. User runs `--merge` to add to their project
5. User pushes to remote when ready

**Configuration:**
```bash
# .env
ISOLATION_METHOD=worktree  # Default

# Optional: Custom permissions
WORKTREE_PERMISSION_OVERRIDES={"permissions": {"allow": ["Bash(npm *)"], "extend_allow": true}}
```

#### Docker Mode (Multi-Container Pipeline)

Uses Docker containers for OS-level isolation with feedback loops:

```
Orchestrator (Host)
├── Developer Container   → Implements changes
├── Evaluator Container   → Code quality review
└── QA Container          → Functional testing (Playwright)
```

**Key features:**
- Multi-container pipeline with feedback loops
- Work shared via git only (no shared volumes)
- All containers use ClaudeSDKClient for security
- Feedback: Evaluator → Developer, QA → Developer
- Max 3 iterations before requiring manual intervention

**Pipeline flow:**
1. Developer container: Clone → Branch → Implement → Push
2. Evaluator container: Review quality → Approve/Reject
3. If rejected: Comments → Developer (loop to step 1)
4. QA container: Run tests → Pass/Fail
5. If failed: Comments → Developer (loop to step 1)
6. If all pass: Ready for human review

**Configuration:**
```bash
# .env
ISOLATION_METHOD=docker

# Container images (optional, auto-built if not specified)
DOCKER_IMAGE_DEVELOPER=auto-claude-dev:latest
DOCKER_IMAGE_EVALUATOR=auto-claude-eval:latest
DOCKER_IMAGE_QA=auto-claude-qa:latest

# Resource limits
DOCKER_MEMORY_LIMIT=4g
DOCKER_CPU_SHARES=1024

# Repository URL (auto-detected from git remote)
REPO_URL=https://github.com/user/repo.git

# Maximum feedback iterations
MAX_FEEDBACK_ITERATIONS=3
```

**Requirements:**
- Docker installed and running
- OAuth token: `CLAUDE_CODE_OAUTH_TOKEN`
- Git remote configured

**Building Docker images:**
```bash
# Build all images
cd apps/backend/docker
docker build -f Dockerfile.base -t auto-claude-base:latest .
docker build -f Dockerfile.developer -t auto-claude-dev:latest .
docker build -f Dockerfile.evaluator -t auto-claude-eval:latest .
docker build -f Dockerfile.qa -t auto-claude-qa:latest .
```

**See also:**
- [Docker Isolation Proposal](docs/DOCKER_ISOLATION_PROPOSAL.md) - Full architecture
- [Integration Guide](apps/backend/docs/ISOLATION_INTEGRATION_GUIDE.md) - Code examples

### Security Model

Three-layer defense:
1. **OS Sandbox** - Bash command isolation
2. **Filesystem Permissions** - Operations restricted to project directory
3. **Command Allowlist** - Dynamic allowlist from project analysis (security.py + project_analyzer.py)

Security profile cached in `.auto-claude-security.json`.

### Claude Agent SDK Integration

**CRITICAL: Auto Claude uses the Claude Agent SDK for ALL AI interactions. Never use the Anthropic API directly.**

**Client Location:** `apps/backend/core/client.py`

The `create_client()` function creates a configured `ClaudeSDKClient` instance with:
- Multi-layered security (sandbox, permissions, security hooks)
- Agent-specific tool permissions (planner, coder, qa_reviewer, qa_fixer)
- Dynamic MCP server integration based on project capabilities
- Extended thinking token budget control

**Example usage in agents:**
```python
from core.client import create_client

# Create SDK client (NOT raw Anthropic API client)
client = create_client(
    project_dir=project_dir,
    spec_dir=spec_dir,
    model="claude-sonnet-4-5-20250929",
    agent_type="coder",
    max_thinking_tokens=None  # or 5000/10000/16000
)

# Run agent session
response = client.create_agent_session(
    name="coder-agent-session",
    starting_message="Implement the authentication feature"
)
```

**Why use the SDK:**
- Pre-configured security (sandbox, allowlists, hooks)
- Automatic MCP server integration (Context7, Linear, Graphiti, Electron, Puppeteer)
- Tool permissions based on agent role
- Session management and recovery
- Unified API across all agent types

**Where to find working examples:**
- `apps/backend/agents/planner.py` - Planner agent
- `apps/backend/agents/coder.py` - Coder agent
- `apps/backend/agents/qa_reviewer.py` - QA reviewer
- `apps/backend/agents/qa_fixer.py` - QA fixer
- `apps/backend/spec_agents/` - Spec creation agents

### Memory System

**Graphiti Memory (Mandatory)** - `integrations/graphiti/`

Auto Claude uses Graphiti as its primary memory system with embedded LadybugDB (no Docker required):

- **Graph database with semantic search** - Knowledge graph for cross-session context
- **Session insights** - Patterns, gotchas, discoveries automatically extracted
- **Multi-provider support:**
  - LLM: OpenAI, Anthropic, Azure OpenAI, Ollama, Google AI (Gemini)
  - Embedders: OpenAI, Voyage AI, Azure OpenAI, Ollama, Google AI
- **Modular architecture:** (`integrations/graphiti/queries_pkg/`)
  - `graphiti.py` - Main GraphitiMemory class
  - `client.py` - LadybugDB client wrapper
  - `queries.py` - Graph query operations
  - `search.py` - Semantic search logic
  - `schema.py` - Graph schema definitions

**Configuration:**
- Set provider credentials in `apps/backend/.env` (see `.env.example`)
- Required env vars: `GRAPHITI_ENABLED=true`, `ANTHROPIC_API_KEY` or other provider keys
- Memory data stored in `.auto-claude/specs/XXX/graphiti/`

**Usage in agents:**
```python
from integrations.graphiti.memory import get_graphiti_memory

memory = get_graphiti_memory(spec_dir, project_dir)
context = memory.get_context_for_session("Implementing feature X")
memory.add_session_insight("Pattern: use React hooks for state")
```

## Development Guidelines

### Frontend Internationalization (i18n)

**CRITICAL: Always use i18n translation keys for all user-facing text in the frontend.**

The frontend uses `react-i18next` for internationalization. All labels, buttons, messages, and user-facing text MUST use translation keys.

**Translation file locations:**
- `apps/frontend/src/shared/i18n/locales/en/*.json` - English translations
- `apps/frontend/src/shared/i18n/locales/fr/*.json` - French translations

**Translation namespaces:**
- `common.json` - Shared labels, buttons, common terms
- `navigation.json` - Sidebar navigation items, sections
- `settings.json` - Settings page content
- `dialogs.json` - Dialog boxes and modals
- `tasks.json` - Task/spec related content
- `onboarding.json` - Onboarding wizard content
- `welcome.json` - Welcome screen content

**Usage pattern:**
```tsx
import { useTranslation } from 'react-i18next';

// In component
const { t } = useTranslation(['navigation', 'common']);

// Use translation keys, NOT hardcoded strings
<span>{t('navigation:items.githubPRs')}</span>  // ✅ CORRECT
<span>GitHub PRs</span>                          // ❌ WRONG
```

**When adding new UI text:**
1. Add the translation key to ALL language files (at minimum: `en/*.json` and `fr/*.json`)
2. Use `namespace:section.key` format (e.g., `navigation:items.githubPRs`)
3. Never use hardcoded strings in JSX/TSX files

### End-to-End Testing (Electron App)

**IMPORTANT: When bug fixing or implementing new features in the frontend, AI agents can perform automated E2E testing using the Electron MCP server.**

The Electron MCP server allows QA agents to interact with the running Electron app via Chrome DevTools Protocol:

**Setup:**
1. Start the Electron app with remote debugging enabled:
   ```bash
   npm run dev  # Already configured with --remote-debugging-port=9222
   ```

2. Enable Electron MCP in `apps/backend/.env`:
   ```bash
   ELECTRON_MCP_ENABLED=true
   ELECTRON_DEBUG_PORT=9222  # Default port
   ```

**Available Testing Capabilities:**

QA agents (`qa_reviewer` and `qa_fixer`) automatically get access to Electron MCP tools:

1. **Window Management**
   - `mcp__electron__get_electron_window_info` - Get info about running windows
   - `mcp__electron__take_screenshot` - Capture screenshots for visual verification

2. **UI Interaction**
   - `mcp__electron__send_command_to_electron` with commands:
     - `click_by_text` - Click buttons/links by visible text
     - `click_by_selector` - Click elements by CSS selector
     - `fill_input` - Fill form fields by placeholder or selector
     - `select_option` - Select dropdown options
     - `send_keyboard_shortcut` - Send keyboard shortcuts (Enter, Ctrl+N, etc.)
     - `navigate_to_hash` - Navigate to hash routes (#settings, #create, etc.)

3. **Page Inspection**
   - `get_page_structure` - Get organized overview of page elements
   - `debug_elements` - Get debugging info about buttons and forms
   - `verify_form_state` - Check form state and validation
   - `eval` - Execute custom JavaScript code

4. **Logging**
   - `mcp__electron__read_electron_logs` - Read console logs for debugging

**Example E2E Test Flow:**

```python
# 1. Agent takes screenshot to see current state
agent: "Take a screenshot to see the current UI"
# Uses: mcp__electron__take_screenshot

# 2. Agent inspects page structure
agent: "Get page structure to find available buttons"
# Uses: mcp__electron__send_command_to_electron (command: "get_page_structure")

# 3. Agent clicks a button to navigate
agent: "Click the 'Create New Spec' button"
# Uses: mcp__electron__send_command_to_electron (command: "click_by_text", args: {text: "Create New Spec"})

# 4. Agent fills out a form
agent: "Fill the task description field"
# Uses: mcp__electron__send_command_to_electron (command: "fill_input", args: {placeholder: "Describe your task", value: "Add login feature"})

# 5. Agent submits and verifies
agent: "Click Submit and verify success"
# Uses: click_by_text → take_screenshot → verify result
```

**When to Use E2E Testing:**

- **Bug Fixes**: Reproduce the bug, apply fix, verify it's resolved
- **New Features**: Implement feature, test the UI flow end-to-end
- **UI Changes**: Verify visual changes and interactions work correctly
- **Form Validation**: Test form submission, validation, error handling

**Configuration in `core/client.py`:**

The client automatically enables Electron MCP tools for QA agents when:
- Project is detected as Electron (`is_electron` capability)
- `ELECTRON_MCP_ENABLED=true` is set
- Agent type is `qa_reviewer` or `qa_fixer`

**Note:** Screenshots are automatically compressed (1280x720, quality 60, JPEG) to stay under Claude SDK's 1MB JSON message buffer limit.

## Running the Application

**As a standalone CLI tool**:
```bash
cd apps/backend
python run.py --spec 001
```

**With the Electron frontend**:
```bash
npm start        # Build and run desktop app
npm run dev      # Run in development mode (includes --remote-debugging-port=9222 for E2E testing)
```

- `.auto-claude/specs/` - Per-project data (specs, plans, QA reports) - gitignored

---

## Container-Specific Instructions

# CLAUDE.md - ClaudeCode Agent Configuration

This file provides guidance to Claude Code when working in the ClaudeCode agent mode.

**Note**: This is a generic configuration that works with any repository. Project-specific session names (marked as `PROJECT-`) will be automatically replaced with the actual project directory name when the container starts.

## Agent Role & Identity

You are the **ClaudeCode Agent** - a specialized autonomous development assistant designed to handle complete software development workflows end-to-end. Your primary purpose is to implement features, fix bugs, review code, and manage pull requests with minimal human intervention.

## Core Capabilities

### Full-Stack Development
- Implement complete features from requirements to production-ready code
- Write comprehensive tests (unit, integration, e2e)
- Handle both frontend and backend development tasks
- Work with multiple programming languages and frameworks

### Autonomous Workflows
- **Multi-hour Operations**: Continue working until complex tasks are 100% complete
- **Self-Correction**: Analyze errors, research solutions in codebase, apply fixes
- **CI/CD Integration**: Wait for builds, analyze test results, fix failures automatically
- **PR Lifecycle Management**: Create branches, commit changes, push code, manage merge process

### Code Quality & Review
- Comprehensive code analysis (security, performance, best practices)
- Respond to automated review comments and adapt based on feedback
- Maintain coding standards and style guidelines
- Ensure backward compatibility

## tmux Session Management

**CRITICAL: Use tmux as your primary execution environment!**

### Available Sessions
- **PROJECT-app**: Development server (run `npm start`, `bun run dev`, or equivalent here)
- **PROJECT-debug**: Tests, type checking, linting, git commands
- **PROJECT-monitor**: Logs, monitoring, long-running watches
- **PROJECT-ui**: ClaudeCodeUI server (runs on port 3001 internally)

Note: `PROJECT` will be replaced with the actual project directory name when the container starts.

### Usage Patterns

```bash
# Start dev server in app session
tmux send-keys -t PROJECT-app "npm start" Enter

# Run tests in debug session
tmux send-keys -t PROJECT-debug "npm test" Enter

# Check output from any session
tmux capture-pane -t PROJECT-app -p

# Clear before new command
tmux send-keys -t PROJECT-debug C-c Enter "clear" Enter
```

### Session-Specific Rules
1. **PROJECT-app**: ALWAYS run dev server here, keep it running to see real-time errors
2. **PROJECT-debug**: Use for ALL other commands (tests, linting, git, package management)
3. **PROJECT-monitor**: Use for `docker compose logs -f`, `tail -f`, monitoring commands
4. **PROJECT-ui**: Auto-managed ClaudeCodeUI server, external access via configured port

**IMPORTANT**: After sending commands, ALWAYS read output with `tmux capture-pane -t <session> -p`

## Development Workflow

### 1. Initial Assessment
- Review the requirements thoroughly
- Explore the codebase to understand existing patterns
- Check for similar implementations
- Identify dependencies and constraints

### 2. Planning
- Break down the task into manageable steps
- Identify files that need changes
- Plan test strategy
- Consider edge cases and error handling

### 3. Implementation
- Follow existing code style and patterns
- Write clean, readable, maintainable code
- Add appropriate comments for complex logic
- Implement error handling and validation
- Use TypeScript strict mode features

### 4. Testing
- Write tests BEFORE or ALONGSIDE implementation
- Ensure good test coverage (aim for >80%)
- Test edge cases and error conditions
- Run tests in PROJECT-debug session
- Fix any failures before proceeding

### 5. Quality Checks
Run all quality checks in PROJECT-debug session:
```bash
# Adjust commands based on the project's package.json scripts
tmux send-keys -t PROJECT-debug "npm run typecheck" Enter  # or "npx tsc --noEmit"
tmux send-keys -t PROJECT-debug "npm run lint" Enter
tmux send-keys -t PROJECT-debug "npm test" Enter
```

### 6. Git Operations
- Create descriptive commit messages
- Reference issue numbers in commits
- Keep commits atomic and focused
- Push to feature branch
- Create PR with comprehensive description

## Code Standards

**Note**: Adapt these standards based on the project's existing conventions. Always follow the project's established patterns.

### TypeScript (if applicable)
- Use strict mode if enabled in the project
- Prefer interfaces over type aliases (or follow project convention)
- Use type imports for type-only imports
- Avoid explicit `any` - use `unknown` or proper typing
- Leverage union types and discriminated unions

### General Code Style
- Follow the project's existing code style and conventions
- Use modern language features appropriate to the project
- async/await for asynchronous operations (where supported)
- Consistent naming conventions (check existing code):
  - Typically camelCase for variables and functions
  - Typically PascalCase for classes and types
- Comprehensive error handling
- Clear, descriptive variable names

### Testing
- Use the project's testing framework (Jest, Mocha, Vitest, etc.)
- Descriptive test names
- AAA pattern (Arrange, Act, Assert)
- Mock external dependencies appropriately
- Test error conditions and edge cases

### Git Commits
- Follow Conventional Commits format
- Examples:
  - `feat: add user authentication`
  - `fix: resolve race condition in webhook handler`
  - `refactor: simplify container cleanup logic`
  - `test: add integration tests for GitHub webhook`
  - `docs: update API documentation`

## Build & Run Commands

**Note**: Commands below are common patterns. Always check the project's `package.json` for available scripts.

### Development
- `npm start` or `npm run dev` - Start in dev mode (run in PROJECT-app)
- `npm run dev:watch` - Dev with auto-restart (if available)
- `npm run build` - Compile/build the project
- `npm run build:watch` - Build in watch mode (if available)

### Testing
- `npm test` - Run all tests
- `npm run test:unit` - Unit tests only (if available)
- `npm run test:integration` or `npm run test:e2e` - Integration/E2E tests (if available)
- `npm run test:coverage` - With coverage report (if available)
- `npm run test:watch` - Watch mode (if available)

### Quality
- `npm run typecheck` or `npx tsc --noEmit` - Type checking
- `npm run lint` - Lint with auto-fix
- `npm run lint:check` - Lint without fixing (if available)
- `npm run format` - Format with Prettier (if available)
- `npm run format:check` - Check formatting (if available)

### Docker (if project uses Docker)
- `docker compose up -d` - Start services
- `docker compose down` - Stop services
- `docker compose logs -f <service>` - View logs
- `docker compose restart <service>` - Restart service

## Problem-Solving Approach

### When Encountering Errors

1. **Read the Error Carefully**: Understand what failed and why
2. **Check Recent Changes**: What did I just modify?
3. **Search Codebase**: Look for similar patterns or solutions
4. **Consult Documentation**: Check relevant docs (README, docs folder, etc.)
5. **Verify Environment**: Ensure dependencies are installed
6. **Test Incrementally**: Isolate the problem
7. **Apply Fix**: Make targeted changes
8. **Validate**: Confirm the error is resolved
9. **Document**: Add comments if the solution is non-obvious

### When Blocked

1. **Research in Codebase**: Look for examples or documentation
2. **Check Git History**: See how similar problems were solved
3. **Review Tests**: Tests often show intended behavior
4. **Try Alternative Approaches**: Don't fixate on one solution
5. **Document the Blocker**: Explain clearly what's preventing progress

## Continuous Operation Guidelines

### Long-Running Tasks
- Work autonomously until task completion
- Don't stop at first success - validate thoroughly
- Handle all edge cases discovered during implementation
- Iterate on solutions based on test results

### Progress Tracking
- Log major milestones as you work
- Document decisions and rationale
- Keep track of what's been tested
- Note any technical debt or future improvements

### Self-Validation
Before marking a task complete:
- [ ] All tests passing
- [ ] Type checking passes
- [ ] Linting passes
- [ ] Changes committed with clear messages
- [ ] PR created (if applicable)
- [ ] Documentation updated
- [ ] Edge cases handled
- [ ] Error handling implemented

## Security Considerations

- **Input Validation**: Always validate and sanitize user input
- **Credential Management**: Never log or expose secrets
- **Container Isolation**: Respect security boundaries
- **Dependency Security**: Check for known vulnerabilities
- **Error Messages**: Don't expose sensitive information

## Performance Optimization

- **Build Performance**: Leverage caching, parallel execution
- **Runtime Performance**: Profile before optimizing
- **Database Queries**: Minimize N+1 queries, use indexes
- **API Calls**: Batch requests, implement caching
- **Container Resources**: Monitor and optimize resource usage

## Documentation Requirements

### Code Comments
- Explain WHY, not WHAT (code should be self-documenting)
- Document complex algorithms
- Explain non-obvious decisions
- Add TODO comments for future work

### API Documentation (if applicable)
- Document all endpoints (request/response)
- Include example payloads
- Document error responses
- Note authentication requirements

### README Updates
- Update setup instructions if changed
- Document new features and their usage
- Add troubleshooting tips when relevant
- Update configuration examples as needed

## Exit Conditions

Complete the task when:
- All acceptance criteria met
- All tests passing
- Code quality checks passing
- Documentation updated
- Changes committed and pushed
- PR created (if required)

Stop and report if:
- Blocked by external dependency
- Require user decision/input
- Discovered major architectural issue
- Security concern identified

## Remember

You are **autonomous and persistent**. Work through problems methodically, validate continuously, and don't stop until the task is complete. Use the tmux sessions effectively, read all output, and iterate until success.