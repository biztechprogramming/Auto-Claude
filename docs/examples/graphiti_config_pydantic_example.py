"""
GraphitiConfig Pydantic Implementation Example
==============================================

This file demonstrates how to refactor GraphitiConfig to use Pydantic,
applying all 13 best practices from:
https://dev.to/devasservice/best-practices-for-using-pydantic-in-python-2021

BEST PRACTICES APPLIED:
1. ✅ Clear Type Annotations - Explicit types for all fields
2. ✅ Optional Fields with Defaults - Field(default=...) pattern
3. ✅ Custom Validators - @field_validator for complex logic
4. ✅ Built-in Validators - Field(ge=0, le=8192) constraints
5. ✅ Nested Models - Proper model composition
6. ✅ Config Classes - model_config for behavior control
7. ✅ Graceful Error Handling - User-friendly error messages
8. ✅ Avoid Redundant Validation - Validate once at creation
9. ✅ Control Validation Timing - validate_assignment=True
10. ✅ Settings Management - BaseSettings for env vars
11. ✅ Avoid Type Mistakes - Runtime type checking
12. ✅ Parse Efficiently - model_validate_json() for JSON
13. ✅ Keep Simple - Declarative field constraints

USAGE:
    # Environment variables (.env file):
    GRAPHITI_ENABLED=true
    GRAPHITI_LLM_PROVIDER=openai
    OPENAI_API_KEY=sk-test-123
    OLLAMA_EMBEDDING_DIM=768

    # Python code:
    try:
        config = GraphitiConfig()  # Auto-loads from .env
        print(f"Using {config.llm_provider} provider")
    except ValidationError as e:
        print(f"Configuration error: {e}")
"""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    ConfigDict,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# BEST PRACTICE #1: Define Clear Type Annotations
# =============================================================================
# Use specific types: Literal for enums, int with constraints, Optional for nullable


class LLMProvider(str, Enum):
    """Supported LLM providers (BP #1: Clear type through Enum)."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"
    GOOGLE = "google"
    OPENROUTER = "openrouter"


class EmbedderProvider(str, Enum):
    """Supported embedder providers (BP #1: Clear type through Enum)."""

    OPENAI = "openai"
    VOYAGE = "voyage"
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"
    GOOGLE = "google"
    OPENROUTER = "openrouter"


# =============================================================================
# BEST PRACTICE #5: Manage Nested Models Effectively
# =============================================================================
# Keep nested structures simple, validate at each level


class OllamaConfig(BaseModel):
    """
    Nested model for Ollama-specific configuration.

    BP #5: Separate nested config into its own model for clarity.
    BP #1: Clear type annotations for all fields.
    BP #2: Optional fields with sensible defaults.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,  # BP #6: Config for whitespace handling
        validate_assignment=True,  # BP #9: Validate on field updates
    )

    base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL",
    )

    llm_model: str = Field(
        default="",
        description="Model for LLM (e.g., deepseek-r1:7b)",
    )

    embedding_model: str = Field(
        default="",
        description="Model for embeddings (e.g., nomic-embed-text)",
    )

    embedding_dim: int = Field(
        default=0,
        ge=0,  # BP #4: Built-in validator for range
        le=8192,  # BP #4: Upper bound validation
        description="Embedding dimension (0 = auto-detect)",
    )

    # BP #3: Custom validator for complex business logic
    @field_validator("embedding_dim", mode="after")
    @classmethod
    def auto_detect_dimension(cls, v: int, info) -> int:
        """
        Auto-detect embedding dimension for known models.

        BP #3: Use field_validator for business logic beyond basic constraints.
        """
        if v > 0:
            return v  # User explicitly set dimension

        # Auto-detect from model name
        model = info.data.get("embedding_model", "").lower()

        if "embeddinggemma" in model or "nomic-embed-text" in model:
            return 768
        elif "mxbai" in model or "bge-large" in model:
            return 1024
        elif "qwen3" in model:
            if "0.6b" in model:
                return 1024
            elif "4b" in model:
                return 2560
            elif "8b" in model:
                return 4096

        return 768  # Default fallback


# =============================================================================
# BEST PRACTICE #10: Use Settings Management for Configuration
# =============================================================================
# Employ BaseSettings to load environment variables with type validation


class GraphitiConfig(BaseSettings):
    """
    Graphiti integration configuration with automatic environment variable loading.

    BP #10: Use BaseSettings for automatic .env loading and type conversion.
    BP #13: Keep models simple and maintainable with declarative constraints.

    Environment Variables:
        GRAPHITI_ENABLED: Enable Graphiti integration (bool)
        GRAPHITI_LLM_PROVIDER: LLM provider (openai|anthropic|azure_openai|ollama|google)
        GRAPHITI_EMBEDDER_PROVIDER: Embedder provider (openai|voyage|azure_openai|ollama|google)
        GRAPHITI_DATABASE: Database name (str)
        GRAPHITI_DB_PATH: Database path (str)
        OPENAI_API_KEY: OpenAI API key (no GRAPHITI_ prefix)
        ANTHROPIC_API_KEY: Anthropic API key
        ... and more (see Field aliases)

    Example:
        ```python
        # .env file:
        GRAPHITI_ENABLED=true
        GRAPHITI_LLM_PROVIDER=openai
        OPENAI_API_KEY=sk-test-123

        # Python:
        config = GraphitiConfig()  # Auto-loads and validates
        ```
    """

    # =============================================================================
    # BEST PRACTICE #6: Configure Models with Config Classes
    # =============================================================================
    # Use model_config to customize validation behavior

    model_config = SettingsConfigDict(
        # BP #10: Auto-load from .env with prefix
        env_prefix="GRAPHITI_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # For nested config (GRAPHITI_OLLAMA__BASE_URL)
        # BP #6: Validation behavior
        str_strip_whitespace=True,  # Auto-strip whitespace
        validate_assignment=True,  # BP #9: Validate on field updates
        validate_default=True,  # Validate default values
        extra="ignore",  # Ignore unknown env vars
        # BP #13: Simplicity
        frozen=False,  # Allow modifications after creation
    )

    # =============================================================================
    # BEST PRACTICE #1: Define Clear Type Annotations
    # BEST PRACTICE #2: Use Optional Fields with Default Values
    # =============================================================================

    # Core settings
    enabled: bool = Field(
        default=False,  # BP #2: Sensible default
        description="Enable Graphiti integration",
    )

    llm_provider: LLMProvider = Field(
        default=LLMProvider.OPENAI,  # BP #2: Type-safe enum default
        description="LLM provider for Graphiti",
    )

    embedder_provider: EmbedderProvider = Field(
        default=EmbedderProvider.OPENAI,
        description="Embedder provider for Graphiti",
    )

    # Database settings
    database: str = Field(
        default="auto_claude_memory",
        min_length=1,  # BP #4: Built-in validator
        description="Graph database name",
    )

    db_path: str = Field(
        default="~/.auto-claude/memories",
        description="Database storage path",
    )

    # =============================================================================
    # BEST PRACTICE #2: Use Optional Fields with Default Values
    # BEST PRACTICE #11: Avoid Type Annotation Mistakes
    # =============================================================================
    # Optional[str] for nullable fields, empty string for required-but-can-be-empty

    # OpenAI settings
    openai_api_key: str = Field(
        default="",
        alias="OPENAI_API_KEY",  # No GRAPHITI_ prefix
        description="OpenAI API key",
    )

    openai_model: str = Field(
        default="gpt-5-mini",
        alias="OPENAI_MODEL",
        description="OpenAI model name",
    )

    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        alias="OPENAI_EMBEDDING_MODEL",
        description="OpenAI embedding model",
    )

    # Anthropic settings
    anthropic_api_key: str = Field(
        default="",
        alias="ANTHROPIC_API_KEY",
        description="Anthropic API key",
    )

    anthropic_model: str = Field(
        default="claude-sonnet-4-5",
        description="Anthropic model name",
    )

    # Azure OpenAI settings
    azure_openai_api_key: str = Field(
        default="",
        alias="AZURE_OPENAI_API_KEY",
        description="Azure OpenAI API key",
    )

    azure_openai_base_url: str = Field(
        default="",
        alias="AZURE_OPENAI_BASE_URL",
        description="Azure OpenAI endpoint URL",
    )

    azure_openai_llm_deployment: str = Field(
        default="",
        alias="AZURE_OPENAI_LLM_DEPLOYMENT",
        description="Azure deployment name for LLM",
    )

    azure_openai_embedding_deployment: str = Field(
        default="",
        alias="AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        description="Azure deployment name for embeddings",
    )

    # Voyage AI settings
    voyage_api_key: str = Field(
        default="",
        alias="VOYAGE_API_KEY",
        description="Voyage AI API key",
    )

    voyage_embedding_model: str = Field(
        default="voyage-3",
        description="Voyage embedding model",
    )

    # Google AI settings
    google_api_key: str = Field(
        default="",
        alias="GOOGLE_API_KEY",
        description="Google AI API key",
    )

    google_llm_model: str = Field(
        default="gemini-2.0-flash",
        description="Google LLM model",
    )

    google_embedding_model: str = Field(
        default="text-embedding-004",
        description="Google embedding model",
    )

    # OpenRouter settings
    openrouter_api_key: str = Field(
        default="",
        alias="OPENROUTER_API_KEY",
        description="OpenRouter API key",
    )

    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter base URL",
    )

    openrouter_llm_model: str = Field(
        default="anthropic/claude-3.5-sonnet",
        description="OpenRouter LLM model",
    )

    openrouter_embedding_model: str = Field(
        default="openai/text-embedding-3-small",
        description="OpenRouter embedding model",
    )

    # =============================================================================
    # BEST PRACTICE #5: Manage Nested Models Effectively
    # =============================================================================
    # Nested Ollama configuration (auto-loaded from GRAPHITI_OLLAMA__* env vars)

    ollama: OllamaConfig = Field(
        default_factory=OllamaConfig,
        description="Ollama-specific configuration",
    )

    # =============================================================================
    # BEST PRACTICE #3: Implement Custom Validators for Complex Logic
    # =============================================================================

    @field_validator("enabled", mode="before")
    @classmethod
    def parse_bool_from_env(cls, v):
        """
        Parse boolean from environment variable strings.

        BP #3: Custom validator for complex parsing logic.
        BP #11: Handle type conversion properly.

        Supports: true, 1, yes, on (case-insensitive)
        """
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("db_path", mode="after")
    @classmethod
    def expand_home_directory(cls, v: str) -> str:
        """
        Expand ~ to home directory.

        BP #3: Custom validator for path normalization.
        """
        return str(Path(v).expanduser())

    # =============================================================================
    # BEST PRACTICE #3: Implement Custom Validators for Complex Logic
    # =============================================================================

    @model_validator(mode="after")
    def validate_provider_credentials(self):
        """
        Validate that provider-specific credentials are present when enabled.

        BP #3: Use model_validator for cross-field validation.
        BP #7: Provide user-friendly error messages.
        """
        if not self.enabled:
            return self  # Skip validation if disabled

        # Validate LLM provider credentials
        if self.llm_provider == LLMProvider.OPENAI:
            if not self.openai_api_key:
                raise ValueError(
                    "OpenAI LLM provider requires OPENAI_API_KEY environment variable"
                )
        elif self.llm_provider == LLMProvider.ANTHROPIC:
            if not self.anthropic_api_key:
                raise ValueError(
                    "Anthropic LLM provider requires ANTHROPIC_API_KEY environment variable"
                )
        elif self.llm_provider == LLMProvider.AZURE_OPENAI:
            if not self.azure_openai_api_key:
                raise ValueError("Azure OpenAI requires AZURE_OPENAI_API_KEY")
            if not self.azure_openai_base_url:
                raise ValueError("Azure OpenAI requires AZURE_OPENAI_BASE_URL")
            if not self.azure_openai_llm_deployment:
                raise ValueError("Azure OpenAI requires AZURE_OPENAI_LLM_DEPLOYMENT")
        elif self.llm_provider == LLMProvider.GOOGLE:
            if not self.google_api_key:
                raise ValueError("Google provider requires GOOGLE_API_KEY")
        elif self.llm_provider == LLMProvider.OPENROUTER:
            if not self.openrouter_api_key:
                raise ValueError("OpenRouter requires OPENROUTER_API_KEY")
        elif self.llm_provider == LLMProvider.OLLAMA:
            if not self.ollama.llm_model:
                raise ValueError("Ollama LLM provider requires OLLAMA_LLM_MODEL")

        # Validate embedder provider credentials
        if self.embedder_provider == EmbedderProvider.OPENAI:
            if not self.openai_api_key:
                raise ValueError("OpenAI embedder requires OPENAI_API_KEY")
        elif self.embedder_provider == EmbedderProvider.VOYAGE:
            if not self.voyage_api_key:
                raise ValueError("Voyage embedder requires VOYAGE_API_KEY")
        elif self.embedder_provider == EmbedderProvider.AZURE_OPENAI:
            if not self.azure_openai_api_key:
                raise ValueError("Azure OpenAI embedder requires AZURE_OPENAI_API_KEY")
            if not self.azure_openai_embedding_deployment:
                raise ValueError(
                    "Azure OpenAI embedder requires AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
                )
        elif self.embedder_provider == EmbedderProvider.GOOGLE:
            if not self.google_api_key:
                raise ValueError("Google embedder requires GOOGLE_API_KEY")
        elif self.embedder_provider == EmbedderProvider.OPENROUTER:
            if not self.openrouter_api_key:
                raise ValueError("OpenRouter embedder requires OPENROUTER_API_KEY")
        elif self.embedder_provider == EmbedderProvider.OLLAMA:
            if not self.ollama.embedding_model:
                raise ValueError("Ollama embedder requires OLLAMA_EMBEDDING_MODEL")

        return self

    # =============================================================================
    # Business Logic Methods (unchanged from original)
    # =============================================================================

    def get_db_path(self) -> Path:
        """
        Get the resolved database path.

        Expands ~ to home directory and appends the database name.
        """
        base_path = Path(self.db_path).expanduser()
        full_path = base_path / self.database
        full_path.parent.mkdir(parents=True, exist_ok=True)
        return full_path

    def get_provider_summary(self) -> str:
        """Get a summary of configured providers."""
        return f"LLM: {self.llm_provider.value}, Embedder: {self.embedder_provider.value}"

    def get_embedding_dimension(self) -> int:
        """
        Get the embedding dimension for the current embedder provider.

        Returns:
            Embedding dimension (e.g., 768, 1024, 1536)
        """
        if self.embedder_provider == EmbedderProvider.OLLAMA:
            return self.ollama.embedding_dim  # Already auto-detected

        dimension_map = {
            EmbedderProvider.OPENAI: 1536,
            EmbedderProvider.VOYAGE: 1024,
            EmbedderProvider.GOOGLE: 768,
            EmbedderProvider.AZURE_OPENAI: 1536,
            EmbedderProvider.OPENROUTER: 1536,
        }

        return dimension_map.get(self.embedder_provider, 768)


# =============================================================================
# BEST PRACTICE #12: Parse Data Efficiently
# =============================================================================
# Example of using model_validate_json() for direct JSON parsing


class GraphitiState(BaseModel):
    """
    State of Graphiti integration for an auto-claude spec.

    BP #12: Use model_validate_json() for efficient JSON parsing.
    BP #1: Clear type annotations for all fields.
    BP #4: Built-in validators for constraints.
    """

    model_config = ConfigDict(
        validate_assignment=True,  # BP #9: Validate on updates
        str_strip_whitespace=True,  # BP #6: Auto-strip whitespace
    )

    initialized: bool = Field(
        default=False,
        description="Whether Graphiti has been initialized",
    )

    database: Optional[str] = Field(
        default=None,
        description="Database name in use",
    )

    episode_count: int = Field(
        default=0,
        ge=0,  # BP #4: Must be non-negative
        description="Number of episodes recorded",
    )

    llm_provider: Optional[str] = Field(
        default=None,
        description="LLM provider in use",
    )

    embedder_provider: Optional[str] = Field(
        default=None,
        description="Embedder provider in use",
    )

    def save(self, spec_dir: Path) -> None:
        """
        Save state to the spec directory.

        BP #12: Use model_dump_json() for efficient serialization.
        """
        marker_file = spec_dir / ".graphiti_state.json"
        marker_file.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, spec_dir: Path) -> Optional["GraphitiState"]:
        """
        Load state from the spec directory.

        BP #12: Use model_validate_json() for efficient parsing.
        BP #7: Handle validation errors gracefully.
        """
        marker_file = spec_dir / ".graphiti_state.json"
        if not marker_file.exists():
            return None

        try:
            return cls.model_validate_json(marker_file.read_text())
        except Exception:
            return None  # Graceful degradation


# =============================================================================
# BEST PRACTICE #7: Handle Validation Errors Gracefully
# =============================================================================
# Example usage with proper error handling


def example_usage():
    """
    Demonstrate proper usage with error handling.

    BP #7: Log errors appropriately and return user-friendly messages.
    """
    from pydantic import ValidationError

    try:
        # BP #10: Auto-loads from .env
        config = GraphitiConfig()

        print(f"✓ Configuration loaded successfully")
        print(f"  Provider: {config.get_provider_summary()}")
        print(f"  Database: {config.database}")

    except ValidationError as e:
        # BP #7: User-friendly error messages
        print(f"✗ Configuration error:")
        for error in e.errors():
            field = error["loc"][0] if error["loc"] else "config"
            message = error["msg"]
            print(f"  - {field}: {message}")

        # Example output:
        # ✗ Configuration error:
        #   - openai_api_key: OpenAI LLM provider requires OPENAI_API_KEY environment variable


if __name__ == "__main__":
    example_usage()
