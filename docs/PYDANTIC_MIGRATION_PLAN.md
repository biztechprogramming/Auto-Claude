# Pydantic Migration Plan

## Executive Summary

This document outlines the migration from dataclasses to Pydantic models for Auto-Claude's configuration and data validation. The migration follows [Pydantic Best Practices 2021](https://dev.to/devasservice/best-practices-for-using-pydantic-in-python-2021).

**TL;DR:** This is a **low-to-medium difficulty** migration that takes **1-2 days** and reduces config code by **40-50%** while improving type safety and developer experience. Start with `LinearConfig` (2 hours) as a proof of concept.

## Difficulty Assessment

### Overall Difficulty: **Low to Medium** 🟢

This migration is **not difficult** - it's mostly mechanical refactoring with high value and low risk.

### Why It's Easy

1. **Mechanical Refactoring** - Most changes are simple patterns:
   - Replace `@dataclass` with Pydantic `BaseSettings`
   - Remove manual `from_env()` methods (Pydantic does this automatically)
   - Remove manual validation (Pydantic validates declaratively)
   - Update import statements

2. **Incremental Migration** - Do one file at a time with backward compatibility:
   - Start with smallest config (`LinearConfig` - 5 fields)
   - Move to larger configs (`GraphitiConfig` - 25+ fields)
   - Keep old API working during transition

3. **Massive Code Reduction**:
   - **GraphitiConfig**: 260 lines → 150 lines (42% reduction)
   - **LinearConfig**: 85 lines → 40 lines (53% reduction)
   - **Eliminate ~100+ lines** of manual validation code

### Time Estimates

| Component | Lines | Complexity | Time | Priority |
|-----------|-------|------------|------|----------|
| LinearConfig | 85→40 | Simple (5 fields) | 1-2 hours | ⭐ Start here |
| GraphitiConfig | 260→150 | Medium (25+ fields) | 3-4 hours | High |
| GraphitiState | 70→50 | Simple (JSON) | 1 hour | Medium |
| LinearProjectState | 80→55 | Simple (JSON) | 1 hour | Medium |
| Testing | - | - | 2-3 hours | High |
| **Total** | **495→295** | **-40%** | **1-2 days** | - |

### What You're Changing

**Current Pattern** (manual, verbose):
```python
@dataclass
class LinearConfig:
    api_key: str
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "LinearConfig":
        api_key = os.environ.get("LINEAR_API_KEY", "")
        return cls(api_key=api_key, enabled=bool(api_key))

    def is_valid(self) -> bool:
        return bool(self.api_key)
```

**Pydantic Pattern** (automatic, concise):
```python
class LinearConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LINEAR_")

    api_key: str = Field(default="", min_length=1)
    enabled: bool = Field(default=True)
    # No from_env(), no is_valid() - Pydantic does it all!
```

### Big Wins

✅ **Eliminate bugs** - Type validation catches config errors at startup
✅ **Less code** - 40-50% reduction in configuration code
✅ **Better DX** - IDE autocomplete, inline documentation
✅ **Self-documenting** - Field descriptions become API docs
✅ **Free JSON schema** - Auto-generate via `model_json_schema()`
✅ **Better errors** - User-friendly validation messages

### Recommended Approach

**Start Small, Prove Value:**

1. **Week 1: LinearConfig** (2 hours)
   - Simplest config, lowest risk
   - See immediate value in reduced code
   - Decision point: Continue or stop?

2. **Week 2: GraphitiConfig** (1 day)
   - Biggest wins (260→150 lines)
   - Most complex validation
   - High impact on maintainability

3. **Week 3: State Models** (1 day)
   - JSON serialization benefits
   - Nice-to-have, not critical

**Stop If:**
- Current code works perfectly and you never touch it
- Team unfamiliar with Pydantic and no time to learn
- About to ship critical release

**Continue If:**
- Want cleaner, more maintainable code
- Tired of manual validation bugs
- Adding new config options frequently

## Benefits

### 1. **Automatic Environment Variable Handling**
- Type coercion (string → bool, int, etc.)
- Required field validation
- Default value management
- Multiple deployment environment support

### 2. **Reduced Code Complexity**
- Eliminate ~100+ lines of manual validation code
- Declarative validation with `@field_validator`
- Automatic error messages

### 3. **Type Safety**
- Runtime type validation
- IDE autocomplete support
- Catch configuration errors at startup, not runtime

### 4. **Better Developer Experience**
- Self-documenting models with Field descriptions
- JSON schema generation for documentation
- Validation error details

## Best Practices Mapping

| Best Practice | Current Issue | Pydantic Solution |
|--------------|---------------|-------------------|
| #1 Clear Type Annotations | Inconsistent typing | Explicit Field types with validation |
| #2 Optional Fields | Manual default handling | `Field(default=...)` with Optional |
| #3 Custom Validators | 60+ lines of validation code | `@field_validator` decorators |
| #4 Built-in Validators | Manual range checks | `Field(ge=0, le=100)` constraints |
| #5 Nested Models | Manual dict handling | Automatic nested model validation |
| #6 Config Classes | No config customization | `model_config` for behavior control |
| #7 Error Handling | Technical error messages | User-friendly ValidationError |
| #8 Redundant Validation | Repeated validation calls | Validate once at creation |
| #9 Validation Timing | Validation on every access | `validate_assignment=True` |
| #10 Settings Management | Manual `os.environ.get()` | `BaseSettings` with auto-loading |
| #11 Type Annotation Mistakes | No runtime validation | Runtime type checking |
| #12 Parse Efficiently | Manual JSON parsing | `model_validate_json()` |
| #13 Keep Simple | Complex validation methods | Declarative field constraints |

## Migration Priority

### Phase 1: Configuration Classes (High Priority)
1. `GraphitiConfig` - Complex validation, 25+ env vars
2. `LinearConfig` - Simpler, good test case
3. `ContainerConfig` - Used in Docker orchestration

### Phase 2: State Management (Medium Priority)
4. `GraphitiState` - JSON serialization benefits
5. `LinearProjectState` - Nested data structures

### Phase 3: Data Models (Low Priority)
6. `FileMatch`, `TaskContext` - Simple dataclasses, may not need migration
7. Workspace models - Keep as dataclasses (minimal validation needed)

## Detailed Migration Examples

### Example 1: GraphitiConfig (Before)

```python
@dataclass
class GraphitiConfig:
    enabled: bool = False
    llm_provider: str = "openai"
    openai_api_key: str = ""
    ollama_embedding_dim: int = 0

    @classmethod
    def from_env(cls) -> "GraphitiConfig":
        enabled_str = os.environ.get("GRAPHITI_ENABLED", "").lower()
        enabled = enabled_str in ("true", "1", "yes")

        llm_provider = os.environ.get("GRAPHITI_LLM_PROVIDER", "openai").lower()
        openai_api_key = os.environ.get("OPENAI_API_KEY", "")

        try:
            ollama_embedding_dim = int(os.environ.get("OLLAMA_EMBEDDING_DIM", "0"))
        except ValueError:
            ollama_embedding_dim = 0

        return cls(
            enabled=enabled,
            llm_provider=llm_provider,
            openai_api_key=openai_api_key,
            ollama_embedding_dim=ollama_embedding_dim,
        )

    def get_validation_errors(self) -> list[str]:
        errors = []
        if not self.enabled:
            errors.append("GRAPHITI_ENABLED must be set to true")
        if self.llm_provider not in ["openai", "anthropic", "azure_openai"]:
            errors.append(f"Invalid LLM provider: {self.llm_provider}")
        if self.llm_provider == "openai" and not self.openai_api_key:
            errors.append("OpenAI provider requires OPENAI_API_KEY")
        return errors
```

**Issues:**
- 40+ lines of manual env var handling
- Manual type coercion with error handling
- Separate validation method
- No validation on field assignment

### Example 1: GraphitiConfig (After - Pydantic)

```python
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class GraphitiConfig(BaseSettings):
    """
    Graphiti integration configuration.

    Automatically loads from environment variables with GRAPHITI_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAPHITI_",
        env_file=".env",
        env_file_encoding="utf-8",
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="ignore",
    )

    # Core settings with automatic env var loading
    enabled: bool = Field(
        default=False,
        description="Enable Graphiti integration"
    )

    llm_provider: Literal["openai", "anthropic", "azure_openai", "ollama", "google"] = Field(
        default="openai",
        description="LLM provider for Graphiti"
    )

    embedder_provider: Literal["openai", "voyage", "azure_openai", "ollama", "google"] = Field(
        default="openai",
        description="Embedder provider for Graphiti"
    )

    # Database settings
    database: str = Field(
        default="auto_claude_memory",
        description="Graph database name"
    )

    db_path: str = Field(
        default="~/.auto-claude/memories",
        description="Database storage path"
    )

    # Provider settings with proper typing
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key",
        alias="OPENAI_API_KEY"  # No GRAPHITI_ prefix for this one
    )

    openai_model: str = Field(
        default="gpt-5-mini",
        alias="OPENAI_MODEL"
    )

    ollama_embedding_dim: int = Field(
        default=0,
        ge=0,
        le=8192,
        description="Ollama embedding dimension (0 = auto-detect)"
    )

    # Custom validators for complex business logic
    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_from_env(cls, v):
        """Parse boolean from environment variable strings."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @model_validator(mode="after")
    def validate_provider_credentials(self):
        """Validate that provider-specific credentials are present."""
        if not self.enabled:
            return self

        # Validate LLM provider credentials
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError("OpenAI LLM provider requires OPENAI_API_KEY")
        elif self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("Anthropic LLM provider requires ANTHROPIC_API_KEY")
        # ... other providers

        return self

    def get_db_path(self) -> Path:
        """Get the resolved database path."""
        base_path = Path(self.db_path).expanduser()
        full_path = base_path / self.database
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path
```

**Benefits:**
- Automatic env var loading (no `from_env()` needed)
- Type validation (string → bool, int)
- Constrained types (`Literal` for enums)
- Field constraints (`ge=0, le=8192`)
- Validation at creation (fail fast)
- Self-documenting with Field descriptions
- 50% less code

**Usage:**
```python
# Before (dataclass)
config = GraphitiConfig.from_env()
if not config.is_valid():
    errors = config.get_validation_errors()
    print(f"Config invalid: {errors}")

# After (Pydantic)
try:
    config = GraphitiConfig()  # Auto-loads from .env
except ValidationError as e:
    print(f"Config invalid: {e}")
```

### Example 2: LinearConfig (Before/After)

**Before:**
```python
@dataclass
class LinearConfig:
    api_key: str
    team_id: str | None = None
    enabled: bool = True

    @classmethod
    def from_env(cls) -> "LinearConfig":
        api_key = os.environ.get("LINEAR_API_KEY", "")
        return cls(
            api_key=api_key,
            team_id=os.environ.get("LINEAR_TEAM_ID"),
            enabled=bool(api_key),
        )

    def is_valid(self) -> bool:
        return bool(self.api_key)
```

**After:**
```python
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class LinearConfig(BaseSettings):
    """Linear integration configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LINEAR_",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    api_key: str = Field(
        default="",
        min_length=1,
        description="Linear API key (required)"
    )

    team_id: str | None = Field(
        default=None,
        description="Linear team ID"
    )

    project_id: str | None = Field(
        default=None,
        description="Linear project ID"
    )

    enabled: bool = Field(
        default=True,
        description="Enable Linear integration"
    )

    @field_validator("enabled", mode="after")
    @classmethod
    def auto_enable_with_api_key(cls, v, info):
        """Auto-enable if API key is present."""
        api_key = info.data.get("api_key", "")
        if api_key and not v:
            return True
        return v

# Usage
config = LinearConfig()  # Auto-loads, validates, fails fast
```

### Example 3: State Models (GraphitiState)

**Before:**
```python
@dataclass
class GraphitiState:
    initialized: bool = False
    episode_count: int = 0
    error_log: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "initialized": self.initialized,
            "episode_count": self.episode_count,
            "error_log": self.error_log[-10:],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GraphitiState":
        return cls(
            initialized=data.get("initialized", False),
            episode_count=data.get("episode_count", 0),
            error_log=data.get("error_log", []),
        )

    def save(self, spec_dir: Path) -> None:
        marker_file = spec_dir / GRAPHITI_STATE_MARKER
        with open(marker_file, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
```

**After:**
```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

class ErrorLogEntry(BaseModel):
    """Single error log entry."""
    timestamp: datetime
    error: str = Field(max_length=500)

class GraphitiState(BaseModel):
    """State of Graphiti integration for an auto-claude spec."""

    model_config = ConfigDict(
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    initialized: bool = Field(
        default=False,
        description="Whether Graphiti has been initialized"
    )

    episode_count: int = Field(
        default=0,
        ge=0,
        description="Number of episodes recorded"
    )

    error_log: list[ErrorLogEntry] = Field(
        default_factory=list,
        max_length=10,
        description="Last 10 errors (auto-truncated)"
    )

    llm_provider: str | None = Field(
        default=None,
        description="LLM provider used"
    )

    @field_validator("error_log", mode="after")
    @classmethod
    def limit_error_log(cls, v):
        """Keep only last 10 errors."""
        return v[-10:] if len(v) > 10 else v

    def save(self, spec_dir: Path) -> None:
        """Save state to the spec directory."""
        marker_file = spec_dir / GRAPHITI_STATE_MARKER
        marker_file.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, spec_dir: Path) -> "GraphitiState | None":
        """Load state from the spec directory."""
        marker_file = spec_dir / GRAPHITI_STATE_MARKER
        if not marker_file.exists():
            return None

        try:
            return cls.model_validate_json(marker_file.read_text())
        except ValidationError:
            return None

# Usage
state = GraphitiState(initialized=True, episode_count=42)
state.save(spec_dir)  # Auto-serializes to JSON

loaded = GraphitiState.load(spec_dir)  # Auto-deserializes, validates
```

**Benefits:**
- No manual `to_dict()`/`from_dict()`
- Use `model_dump_json()` and `model_validate_json()`
- Nested model validation (ErrorLogEntry)
- Automatic JSON schema generation

## Implementation Steps

### Step 1: Add Pydantic to Dependencies

```bash
# Add to requirements.txt
pydantic>=2.0.0
pydantic-settings>=2.0.0
```

### Step 2: Migrate GraphitiConfig

1. Create `apps/backend/integrations/graphiti/config_v2.py`
2. Implement Pydantic version
3. Add tests in `tests/test_graphiti_config.py`
4. Update imports when validated

### Step 3: Migrate LinearConfig

1. Create `apps/backend/integrations/linear/config_v2.py`
2. Implement Pydantic version
3. Add tests
4. Update imports

### Step 4: Migrate State Models

1. Update `GraphitiState` and `LinearProjectState`
2. Ensure JSON serialization compatibility
3. Test load/save operations

### Step 5: Update Consumers

1. Replace `Config.from_env()` with `Config()`
2. Replace `if not config.is_valid()` with try/except ValidationError
3. Update validation error handling

## Testing Strategy

### Unit Tests

```python
import pytest
from pydantic import ValidationError

def test_graphiti_config_auto_loads_env_vars(monkeypatch):
    """Test that config auto-loads from environment."""
    monkeypatch.setenv("GRAPHITI_ENABLED", "true")
    monkeypatch.setenv("GRAPHITI_LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

    config = GraphitiConfig()

    assert config.enabled is True
    assert config.llm_provider == "openai"
    assert config.openai_api_key == "sk-test-key"

def test_graphiti_config_validates_provider():
    """Test that invalid provider raises error."""
    with pytest.raises(ValidationError) as exc_info:
        GraphitiConfig(
            enabled=True,
            llm_provider="invalid_provider"
        )

    assert "llm_provider" in str(exc_info.value)

def test_graphiti_config_requires_api_key_when_enabled():
    """Test that enabled config requires API key."""
    with pytest.raises(ValidationError) as exc_info:
        GraphitiConfig(
            enabled=True,
            llm_provider="openai",
            openai_api_key=""  # Missing key
        )

    assert "OPENAI_API_KEY" in str(exc_info.value)

def test_graphiti_state_json_roundtrip():
    """Test state can be saved and loaded."""
    state = GraphitiState(
        initialized=True,
        episode_count=10,
        llm_provider="openai"
    )

    # Serialize
    json_str = state.model_dump_json()

    # Deserialize
    loaded = GraphitiState.model_validate_json(json_str)

    assert loaded.initialized == state.initialized
    assert loaded.episode_count == state.episode_count
    assert loaded.llm_provider == state.llm_provider
```

## Backward Compatibility

To maintain compatibility during migration:

```python
# config.py - Temporary compatibility layer
from .config_v2 import GraphitiConfig as GraphitiConfigV2

class GraphitiConfig(GraphitiConfigV2):
    """Backward compatibility wrapper."""

    @classmethod
    def from_env(cls) -> "GraphitiConfig":
        """Legacy method - now just creates instance."""
        return cls()

    def is_valid(self) -> bool:
        """Legacy method - Pydantic validates at creation."""
        return self.enabled

    def get_validation_errors(self) -> list[str]:
        """Legacy method - errors raised at creation now."""
        # Config is valid if we got here
        return []
```

## Rollout Plan

### Week 1: Foundation
- [ ] Add Pydantic dependencies
- [ ] Create migration plan document
- [ ] Set up test framework

### Week 2: Config Migration
- [ ] Migrate GraphitiConfig
- [ ] Migrate LinearConfig
- [ ] Update all config consumers

### Week 3: State Migration
- [ ] Migrate GraphitiState
- [ ] Migrate LinearProjectState
- [ ] Test JSON serialization

### Week 4: Testing & Cleanup
- [ ] Comprehensive integration tests
- [ ] Remove backward compatibility layer
- [ ] Update documentation

## References

- [Pydantic Best Practices 2021](https://dev.to/devasservice/best-practices-for-using-pydantic-in-python-2021)
- [Pydantic Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [Pydantic V2 Migration Guide](https://docs.pydantic.dev/latest/migration/)
