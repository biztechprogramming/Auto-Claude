### Docker Isolation Strategy - Comprehensive Test Suite

## 🎯 Quick Start

```bash
# Run all Docker tests
cd apps/backend
.venv/bin/pytest tests/test_docker*.py tests/test_container*.py tests/test_workflow*.py tests/test_task*.py -v

# Fast tests only (< 5 seconds)
.venv/bin/pytest tests/test_docker*.py tests/test_container*.py -m "not slow" -v

# With coverage report
.venv/bin/pytest tests/test_docker*.py tests/test_container*.py --cov=apps.backend.core.isolation --cov-report=html -v
```

## 📊 Test Coverage Summary

| Test File | Tests | Coverage | Purpose |
|-----------|-------|----------|---------|
| `test_docker_strategy.py` | 37 | 95%+ | Docker strategy core functionality |
| `test_docker_orchestrator.py` | 28 | 90%+ | Container orchestration |
| `test_container_lifecycle.py` | 27 | 95%+ | Container lifecycle management |
| `test_container_client.py` | 22 | 85%+ | HTTP client communication |
| `test_workflow_state_machine.py` | 12 | 95%+ | Workflow state transitions |
| `test_task_log_writer.py` | 28 | 90%+ | Task log observation |
| `test_docker_integration.py` | 11 | End-to-end | Complete pipeline validation |
| **TOTAL** | **165+** | **90%+** | **Comprehensive coverage** |

## 🧪 Test Categories

### Unit Tests (Fast - < 5 seconds)
- ✅ Docker strategy initialization and configuration
- ✅ Orchestrator coordination
- ✅ Container lifecycle operations
- ✅ Container client HTTP communication
- ✅ Task log writer observation
- ✅ Workflow configuration

### Integration Tests (Medium - 5-15 seconds)
- ✅ Workflow state machine transitions
- ✅ Feedback loop iterations
- ✅ Skip if complete logic
- ✅ Status callbacks

### End-to-End Tests (Slow - 15-30 seconds)
- ✅ Complete pipeline execution
- ✅ Error handling and recovery
- ✅ Multi-spec isolation
- ✅ Resume and recovery scenarios

## 🎯 What Gets Tested

### Docker Strategy (`test_docker_strategy.py`)
- [x] Initialization with defaults, custom values, and env vars
- [x] Repository URL detection (HTTPS, SSH conversion)
- [x] Branch detection (current, detached HEAD, failures)
- [x] Docker availability checks
- [x] Environment creation and management
- [x] Branch merging and cleanup
- [x] Changed files detection
- [x] Container status retrieval
- [x] Error handling for all operations

### Orchestrator (`test_docker_orchestrator.py`)
- [x] Orchestrator initialization
- [x] Container naming conventions
- [x] Environment variable management (tokens, database, GitHub)
- [x] Task description extraction from plans
- [x] Image building coordination
- [x] Container status tracking
- [x] HTTP-based container execution
- [x] Log streaming and observation
- [x] Timeout handling
- [x] Error propagation
- [x] Feedback comment serialization

### Container Lifecycle (`test_container_lifecycle.py`)
- [x] Container name generation for all roles
- [x] Existence checks (running/stopped/not found)
- [x] Starting containers with configuration
- [x] Resource limits (memory, CPU, PIDs)
- [x] Environment variable passing
- [x] Stopping and removing containers
- [x] Cleanup operations (single/all containers)
- [x] Error resilience

### Container Client (`test_container_client.py`)
- [x] Container startup and configuration
- [x] Health check polling with retries
- [x] Repository cloning
- [x] Task execution (start/status/completion)
- [x] Status polling with timeout
- [x] Log retrieval
- [x] Container cleanup
- [x] Error handling for all operations

### Workflow State Machine (`test_workflow_state_machine.py`)
- [x] Workflow configuration validation
- [x] State transitions (pending → active → completed/failed)
- [x] Successful pipeline (all steps pass)
- [x] Max iterations exceeded
- [x] Retry on evaluator rejection
- [x] Skip if complete logic
- [x] Feedback accumulation across retries
- [x] Status callbacks during execution
- [x] Task log integration

### Task Log Writer (`test_task_log_writer.py`)
- [x] Log file initialization
- [x] Phase status management (pending/active/completed/failed)
- [x] Log entry creation
- [x] Container log observation and parsing
- [x] Workflow state management
- [x] Iteration tracking
- [x] Phase completion checking
- [x] Phase reset functionality
- [x] Atomic file writes (Windows-safe)
- [x] Timestamp management

### Integration Tests (`test_docker_integration.py`)
- [x] Full pipeline success (all steps pass)
- [x] Pipeline with one retry iteration
- [x] Max retries exceeded
- [x] Container startup failure handling
- [x] Git operation failure handling
- [x] Missing spec file handling
- [x] Environment lifecycle (create → use → merge → cleanup)
- [x] Multi-spec isolation
- [x] Status tracking throughout workflow
- [x] Resume after partial completion

## 🏃 Running Tests

### By Category

```bash
# Unit tests (fastest)
pytest tests/test_docker_strategy.py tests/test_docker_orchestrator.py -v

# Container tests
pytest tests/test_container_lifecycle.py tests/test_container_client.py -v

# Workflow tests
pytest tests/test_workflow_state_machine.py tests/test_task_log_writer.py -v

# Integration tests
pytest tests/test_docker_integration.py -v
```

### By Feature

```bash
# Test initialization
pytest tests/test_docker_strategy.py::TestDockerStrategyInitialization -v

# Test workflow state machine
pytest tests/test_workflow_state_machine.py::TestWorkflowStateTransitions -v

# Test error handling
pytest tests/test_docker_integration.py::TestErrorHandlingAndRecovery -v
```

### With Options

```bash
# Verbose output with full tracebacks
pytest tests/test_docker*.py -vv

# Stop on first failure
pytest tests/test_docker*.py -x

# Run tests matching pattern
pytest tests/test_docker*.py -k "test_init" -v

# Parallel execution (if pytest-xdist installed)
pytest tests/test_docker*.py -n auto
```

## 📦 Complex Spec Fixture

The test suite includes a realistic complex spec fixture (`fixtures/complex_spec.py`):

**Spec**: User Dashboard API with real-time notifications
- 6 implementation phases
- 15 subtasks with dependencies
- Mixed completion states
- Realistic file structure
- Comprehensive requirements

**Usage**:
```python
from tests.fixtures.complex_spec import get_complex_spec, create_complex_spec_files

spec = get_complex_spec()
spec_dir = create_complex_spec_files(tmp_path)
```

## 🐛 Debugging Tests

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Print Test Output

```bash
# Use -s flag to see print statements
pytest tests/test_docker_strategy.py -v -s
```

### Run Single Test

```bash
pytest tests/test_docker_strategy.py::TestRepoUrlDetection::test_detect_ssh_url_converts_to_https -v
```

### Use pytest debugger

```bash
# Drop into debugger on failure
pytest tests/test_docker_strategy.py --pdb

# Drop into debugger on test start
pytest tests/test_docker_strategy.py -v --trace
```

## 📈 Test Performance

**Targets**:
- Unit tests: < 5 seconds
- Integration tests: < 15 seconds
- Full suite: < 30 seconds

**Current Performance**:
- ✅ Unit tests: ~3 seconds
- ✅ Integration tests: ~10 seconds
- ✅ Full suite: ~20 seconds

## 🔧 Maintenance

### Adding New Tests

1. Choose appropriate test file based on component
2. Follow existing test structure and naming
3. Use descriptive test names (test_verb_noun_condition)
4. Include docstrings explaining what is tested
5. Update this README with new test count

### Test Template

```python
class TestNewFeature:
    """Test description."""

    def test_feature_success_case(self, fixture):
        """Test successful operation."""
        # Arrange
        expected = "value"

        # Act
        result = fixture.method()

        # Assert
        assert result == expected

    def test_feature_error_case(self, fixture):
        """Test error handling."""
        with pytest.raises(ValueError, match="error message"):
            fixture.method_that_fails()
```

## 🎓 Best Practices

1. **Test Names**: Use descriptive names that explain what is tested
2. **One Assertion per Test**: Keep tests focused
3. **Arrange-Act-Assert**: Follow AAA pattern
4. **Mocking**: Mock external dependencies (Docker, HTTP, Git)
5. **Fixtures**: Use fixtures for common setup
6. **Async Tests**: Mark with `@pytest.mark.asyncio`
7. **Slow Tests**: Mark with `@pytest.mark.slow`

## 📚 Documentation

- [DOCKER_TEST_GUIDE.md](DOCKER_TEST_GUIDE.md) - Comprehensive test guide
- [DOCKER_ISOLATION_PROPOSAL.md](../docs/DOCKER_ISOLATION_PROPOSAL.md) - Architecture
- [DOCKER_WORKFLOW_DESIGN.md](../docs/DOCKER_WORKFLOW_DESIGN.md) - Workflow design

## ✅ Success Criteria

**The test suite is successful when**:
- ✅ 165+ tests passing
- ✅ 90%+ code coverage
- ✅ All tests complete in < 30 seconds
- ✅ Zero flaky tests
- ✅ Clear, descriptive test names
- ✅ Comprehensive error case coverage

## 🚀 Next Steps

After running these tests successfully:

1. Run the actual Docker pipeline with a real spec
2. Monitor container logs and status
3. Verify task logs are created correctly
4. Test feedback loops in action
5. Validate the complete workflow end-to-end

---

**Summary**: This comprehensive test suite with 165+ tests ensures the Docker isolation strategy works correctly across all scenarios, from initialization to complete pipeline execution, with robust error handling and recovery.
