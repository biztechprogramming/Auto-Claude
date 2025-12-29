# Docker Test Failure Root Cause Analysis

## Summary

21 tests are failing across two test files:
- `test_docker_strategy.py`: 11 failures
- `test_docker_orchestrator.py`: 10 failures

## Root Causes Identified

### 1. Mock Attribute Errors (7 failures)

**Problem**: Tests are trying to mock attributes that don't exist in the implementation.

**Affected Tests**:
- `test_docker_strategy.py`:
  - `test_setup_success` - mocking `_orchestrator` (line 239)
  - `test_remove_environment_no_branch_cleanup` - mocking `_orchestrator` (line 340)
  - `test_remove_environment_with_branch_cleanup` - mocking `_orchestrator` (line 349)
  - `test_merge_changes_success` - mocking `_orchestrator` (line 372)
  - `test_merge_changes_with_delete` - mocking `_orchestrator` (line 384)
  - `test_get_container_status` - mocking `_orchestrator` (line 491)

- `test_docker_orchestrator.py`:
  - `test_build_images_delegates_to_builder` - mocking `image_builder` (line 219)
  - `test_build_images_with_force` - mocking `image_builder` (line 232)
  - `test_get_container_status_all_running` - mocking `container_manager` (line 247)
  - `test_get_container_status_mixed` - mocking `container_manager` (line 262)
  - `test_cleanup_containers_delegates` - mocking `container_manager` (line 281)

**Root Cause**: The implementation DOES have these attributes:

```python
# orchestrator.py line 53-57
self.image_builder = ImageBuilder()
self.container_manager = ContainerLifecycleManager(...)

# docker_strategy.py line 118
self._orchestrator = DockerOrchestrator(...)
```

The tests are using `@patch.object(ClassName, 'attribute_name')` which is **the wrong pattern** for mocking instance attributes. This pattern is for class-level attributes or methods, not instance attributes created in `__init__`.

**Fix Required**:
- Use `@patch('module.path.ClassName')` to mock the class constructor instead
- OR access the instance attribute directly without patching
- OR use `monkeypatch` fixture to set the attribute on the instance

### 2. Repository URL Detection Failures (3 failures)

**Problem**: Tests don't provide `repo_url` or mock the git command that detects it.

**Affected Tests**:
- `test_init_with_defaults` (line 27)
- `test_init_with_custom_values` (line 38)
- `test_init_explicit_overrides_env` (line 79)

**Root Cause**: `DockerIsolationStrategy.__init__()` calls `_detect_repo_url()` which runs:

```python
# docker_strategy.py line 93
self.repo_url = repo_url or os.getenv("REPO_URL") or self._detect_repo_url()
```

The `_detect_repo_url()` method runs `git remote get-url origin` which fails in test fixtures.

**Fix Required**:
- Provide explicit `repo_url` parameter
- OR mock `subprocess.run` to return a fake URL
- OR set `REPO_URL` environment variable using `monkeypatch`

### 3. Base Branch Detection Failure (1 failure)

**Problem**: Test expects `base_branch` to be set but initialization sets it to `None`.

**Affected Test**:
- `test_detect_current_branch` (line 154)

**Root Cause**: The test mocks `subprocess.run` to return "feature/test" but doesn't account for the initialization logic:

```python
# docker_strategy.py line 104-106
if not base_branch:
    base_branch = self._detect_base_branch()
```

The test passes `repo_url` but not `base_branch`, so `_detect_base_branch()` should be called. However, the mock setup is incomplete.

**Fix Required**:
- Mock `subprocess.run` to handle BOTH the repo URL detection AND branch detection calls
- OR provide explicit `base_branch` parameter

### 4. Workflow Configuration Errors (5 failures)

**Problem**: `_run_container_http` looks up workflow configuration but can't find the role.

**Affected Tests**:
- `test_run_container_http_success` - ContainerRole.DEVELOPER (line 326)
- `test_run_container_http_api_not_ready` - ContainerRole.DEVELOPER (line 353)
- `test_run_container_http_task_timeout` - ContainerRole.QA (line 383)
- `test_run_container_http_task_fails` - ContainerRole.QA (line 420)
- `test_run_container_http_with_feedback` - ContainerRole.DEVELOPER (line 462)

**Root Cause**: The implementation changed to use workflow configuration:

```python
# orchestrator.py line 152-156
from core.isolation.workflow_config import get_step_by_role
step = get_step_by_role(role)
if not step:
    raise ValueError(f"No workflow step found for role: {role}")
```

The tests don't mock `workflow_config` module, so `get_step_by_role()` returns `None`.

**Fix Required**:
- Mock `core.isolation.workflow_config.get_step_by_role` to return a valid workflow step
- Include required step attributes: `port`, `log_phase`, etc.

### 5. StopIteration Error (1 failure)

**Problem**: Iteration over mock return values exhausted.

**Affected Test**:
- `test_merge_changes_merge_fails` (line 406)

**Root Cause**: The test uses `side_effect` list with 2 items but code makes more than 2 calls to `subprocess.run`:

```python
# Test line 409-412
mock_run.side_effect = [
    Mock(returncode=0, stderr=""),  # checkout
    Mock(returncode=1, stderr="merge conflict")  # merge
]
```

But the implementation also calls `git merge --abort` which is a 3rd call.

**Fix Required**:
- Add a 3rd mock return value for the `--abort` call
- OR use `return_value` instead of `side_effect`

## Summary by Category

| Category | Count | Fix Complexity |
|----------|-------|----------------|
| Mock Pattern Errors | 11 | Medium - requires understanding Python mocking |
| Missing Test Setup | 4 | Easy - add mocks or parameters |
| Workflow Config | 5 | Easy - add workflow config mock |
| Side Effect Exhaustion | 1 | Trivial - add one more mock value |

## Recommended Fix Order

1. **Fix Repository URL detection** (3 tests) - Easiest, affects initialization
2. **Fix Base Branch detection** (1 test) - Similar to above
3. **Fix Mock Patterns** (11 tests) - Core issue affecting many tests
4. **Fix Workflow Config** (5 tests) - New dependency that needs mocking
5. **Fix StopIteration** (1 test) - Trivial fix

## Next Steps

1. Create a comprehensive test fixture that handles:
   - Mocked git commands for repo URL and branch detection
   - Workflow configuration mocks
   - Proper instance attribute access (not mocking)

2. Update individual tests to:
   - Provide explicit parameters where possible
   - Use correct mocking patterns
   - Mock new dependencies (workflow_config)

3. Run tests incrementally after each category is fixed
