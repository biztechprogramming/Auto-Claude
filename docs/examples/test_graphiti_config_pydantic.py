"""
Test Suite for Pydantic GraphitiConfig
======================================

Demonstrates testing strategies for Pydantic models with best practices.
"""

import pytest
from pathlib import Path
from pydantic import ValidationError

# Import the Pydantic config (when implemented)
# from apps.backend.integrations.graphiti.config_v2 import (
#     GraphitiConfig,
#     GraphitiState,
#     OllamaConfig,
#     LLMProvider,
#     EmbedderProvider,
# )


class TestGraphitiConfigBasics:
    """Test basic configuration loading and validation."""

    def test_config_loads_with_defaults(self):
        """Test that config can be created with all defaults."""
        config = GraphitiConfig()

        assert config.enabled is False
        assert config.llm_provider == LLMProvider.OPENAI
        assert config.database == "auto_claude_memory"
        assert config.db_path.endswith("/.auto-claude/memories")

    def test_config_auto_loads_from_env(self, monkeypatch):
        """Test automatic environment variable loading."""
        monkeypatch.setenv("GRAPHITI_ENABLED", "true")
        monkeypatch.setenv("GRAPHITI_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-123")

        config = GraphitiConfig()

        assert config.enabled is True
        assert config.llm_provider == LLMProvider.ANTHROPIC
        assert config.anthropic_api_key == "sk-ant-test-123"

    def test_config_respects_env_file(self, tmp_path, monkeypatch):
        """Test loading from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            """
            GRAPHITI_ENABLED=true
            GRAPHITI_LLM_PROVIDER=openai
            OPENAI_API_KEY=sk-test-from-file
            """
        )

        monkeypatch.chdir(tmp_path)
        config = GraphitiConfig()

        assert config.enabled is True
        assert config.openai_api_key == "sk-test-from-file"

    def test_config_strips_whitespace(self, monkeypatch):
        """Test that whitespace is automatically stripped."""
        monkeypatch.setenv("OPENAI_API_KEY", "  sk-test-123  ")
        monkeypatch.setenv("GRAPHITI_DATABASE", "  my_database  ")

        config = GraphitiConfig()

        assert config.openai_api_key == "sk-test-123"
        assert config.database == "my_database"


class TestGraphitiConfigValidation:
    """Test validation logic and error handling."""

    def test_invalid_llm_provider_raises_error(self):
        """Test that invalid provider is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(llm_provider="invalid_provider")

        errors = exc_info.value.errors()
        assert any("llm_provider" in str(e) for e in errors)

    def test_enabled_config_requires_provider_credentials(self):
        """Test that enabled config validates provider credentials."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                enabled=True,
                llm_provider=LLMProvider.OPENAI,
                openai_api_key="",  # Missing!
            )

        error_msg = str(exc_info.value)
        assert "OPENAI_API_KEY" in error_msg

    def test_anthropic_provider_requires_api_key(self):
        """Test Anthropic-specific validation."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                enabled=True,
                llm_provider=LLMProvider.ANTHROPIC,
                anthropic_api_key="",  # Missing!
            )

        error_msg = str(exc_info.value)
        assert "ANTHROPIC_API_KEY" in error_msg

    def test_azure_provider_requires_all_fields(self):
        """Test Azure OpenAI requires complete configuration."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                enabled=True,
                llm_provider=LLMProvider.AZURE_OPENAI,
                azure_openai_api_key="test-key",
                azure_openai_base_url="",  # Missing!
            )

        error_msg = str(exc_info.value)
        assert "AZURE_OPENAI_BASE_URL" in error_msg

    def test_disabled_config_skips_validation(self):
        """Test that disabled config doesn't validate credentials."""
        # Should not raise even with missing credentials
        config = GraphitiConfig(
            enabled=False,
            llm_provider=LLMProvider.OPENAI,
            openai_api_key="",  # Missing but OK since disabled
        )

        assert config.enabled is False


class TestGraphitiConfigTypeCoercion:
    """Test automatic type coercion and parsing."""

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("0", False),
            ("no", False),
            ("", False),
        ],
    )
    def test_bool_parsing_from_env(self, env_value, expected, monkeypatch):
        """Test various boolean string formats are parsed correctly."""
        monkeypatch.setenv("GRAPHITI_ENABLED", env_value)

        config = GraphitiConfig()

        assert config.enabled is expected

    def test_int_parsing_from_env(self, monkeypatch):
        """Test integer parsing from environment."""
        monkeypatch.setenv("GRAPHITI_OLLAMA__EMBEDDING_DIM", "768")

        config = GraphitiConfig()

        assert config.ollama.embedding_dim == 768
        assert isinstance(config.ollama.embedding_dim, int)

    def test_invalid_int_raises_error(self, monkeypatch):
        """Test that invalid integer raises validation error."""
        monkeypatch.setenv("GRAPHITI_OLLAMA__EMBEDDING_DIM", "not-a-number")

        with pytest.raises(ValidationError):
            GraphitiConfig()


class TestGraphitiConfigConstraints:
    """Test field constraints and validators."""

    def test_embedding_dim_must_be_non_negative(self):
        """Test that embedding dimension must be >= 0."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                ollama=OllamaConfig(embedding_dim=-1)
            )

        error_msg = str(exc_info.value)
        assert "greater than or equal to 0" in error_msg

    def test_embedding_dim_has_upper_limit(self):
        """Test that embedding dimension has reasonable upper limit."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                ollama=OllamaConfig(embedding_dim=9999)
            )

        error_msg = str(exc_info.value)
        assert "less than or equal to" in error_msg

    def test_database_name_cannot_be_empty(self):
        """Test that database name must have at least 1 character."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(database="")

        error_msg = str(exc_info.value)
        assert "at least 1 character" in error_msg


class TestOllamaConfigNested:
    """Test nested Ollama configuration."""

    def test_ollama_config_auto_detects_embedding_dimension(self):
        """Test automatic dimension detection for known models."""
        test_cases = [
            ("nomic-embed-text", 768),
            ("embeddinggemma", 768),
            ("mxbai-embed-large", 1024),
            ("bge-large", 1024),
            ("qwen3-embedding:0.6b", 1024),
            ("qwen3-embedding:4b", 2560),
            ("qwen3-embedding:8b", 4096),
            ("unknown-model", 768),  # Default fallback
        ]

        for model_name, expected_dim in test_cases:
            config = OllamaConfig(embedding_model=model_name)
            assert config.embedding_dim == expected_dim, \
                f"Model {model_name} should have dim {expected_dim}"

    def test_ollama_config_respects_explicit_dimension(self):
        """Test that explicit dimension overrides auto-detection."""
        config = OllamaConfig(
            embedding_model="nomic-embed-text",  # Would auto-detect 768
            embedding_dim=1024  # Explicit override
        )

        assert config.embedding_dim == 1024

    def test_ollama_config_loads_from_nested_env_vars(self, monkeypatch):
        """Test loading nested config from environment."""
        monkeypatch.setenv("GRAPHITI_OLLAMA__BASE_URL", "http://localhost:11434")
        monkeypatch.setenv("GRAPHITI_OLLAMA__LLM_MODEL", "deepseek-r1:7b")
        monkeypatch.setenv("GRAPHITI_OLLAMA__EMBEDDING_MODEL", "nomic-embed-text")

        config = GraphitiConfig()

        assert config.ollama.base_url == "http://localhost:11434"
        assert config.ollama.llm_model == "deepseek-r1:7b"
        assert config.ollama.embedding_model == "nomic-embed-text"


class TestGraphitiConfigBusinessLogic:
    """Test business logic methods on config."""

    def test_get_db_path_expands_home_directory(self):
        """Test that ~ is expanded to home directory."""
        config = GraphitiConfig(db_path="~/.auto-claude/test")

        db_path = config.get_db_path()

        assert "~" not in str(db_path)
        assert db_path.is_absolute()

    def test_get_db_path_creates_parent_directory(self, tmp_path):
        """Test that parent directory is created."""
        config = GraphitiConfig(
            db_path=str(tmp_path / "new_dir" / "memories"),
            database="test_db"
        )

        db_path = config.get_db_path()

        assert db_path.parent.exists()
        assert db_path.parent.is_dir()

    def test_get_provider_summary(self):
        """Test provider summary generation."""
        config = GraphitiConfig(
            llm_provider=LLMProvider.ANTHROPIC,
            embedder_provider=EmbedderProvider.VOYAGE
        )

        summary = config.get_provider_summary()

        assert "anthropic" in summary.lower()
        assert "voyage" in summary.lower()

    def test_get_embedding_dimension_for_different_providers(self):
        """Test embedding dimension retrieval for all providers."""
        test_cases = [
            (EmbedderProvider.OPENAI, 1536),
            (EmbedderProvider.VOYAGE, 1024),
            (EmbedderProvider.GOOGLE, 768),
            (EmbedderProvider.AZURE_OPENAI, 1536),
            (EmbedderProvider.OPENROUTER, 1536),
        ]

        for provider, expected_dim in test_cases:
            config = GraphitiConfig(embedder_provider=provider)
            assert config.get_embedding_dimension() == expected_dim


class TestGraphitiState:
    """Test GraphitiState model (JSON serialization)."""

    def test_state_json_round_trip(self):
        """Test state can be serialized and deserialized."""
        state = GraphitiState(
            initialized=True,
            database="test_db",
            episode_count=42,
            llm_provider="openai",
        )

        # Serialize to JSON
        json_str = state.model_dump_json()

        # Deserialize from JSON
        loaded = GraphitiState.model_validate_json(json_str)

        assert loaded.initialized == state.initialized
        assert loaded.database == state.database
        assert loaded.episode_count == state.episode_count
        assert loaded.llm_provider == state.llm_provider

    def test_state_save_and_load(self, tmp_path):
        """Test saving and loading state from filesystem."""
        spec_dir = tmp_path / "spec-001"
        spec_dir.mkdir()

        state = GraphitiState(
            initialized=True,
            episode_count=10,
        )

        # Save
        state.save(spec_dir)

        # Load
        loaded = GraphitiState.load(spec_dir)

        assert loaded is not None
        assert loaded.initialized is True
        assert loaded.episode_count == 10

    def test_state_load_returns_none_if_missing(self, tmp_path):
        """Test that load returns None if state file doesn't exist."""
        loaded = GraphitiState.load(tmp_path)

        assert loaded is None

    def test_state_episode_count_must_be_non_negative(self):
        """Test episode count validation."""
        with pytest.raises(ValidationError):
            GraphitiState(episode_count=-1)


class TestGraphitiConfigValidationMessages:
    """Test that validation errors have user-friendly messages."""

    def test_missing_openai_key_message(self):
        """Test error message for missing OpenAI key is helpful."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(
                enabled=True,
                llm_provider=LLMProvider.OPENAI,
                openai_api_key="",
            )

        error_msg = str(exc_info.value)

        # Should mention what's missing and where to set it
        assert "OPENAI_API_KEY" in error_msg
        assert "environment variable" in error_msg.lower()

    def test_invalid_provider_message(self):
        """Test error message for invalid provider is clear."""
        with pytest.raises(ValidationError) as exc_info:
            GraphitiConfig(llm_provider="bad_provider")

        error_msg = str(exc_info.value)

        # Should show valid options
        assert "llm_provider" in error_msg


class TestConfigurationReassignment:
    """Test validate_assignment behavior."""

    def test_config_validates_on_field_update(self):
        """Test that changing a field triggers validation."""
        config = GraphitiConfig()

        # Should raise error when setting to invalid value
        with pytest.raises(ValidationError):
            config.ollama.embedding_dim = -100

    def test_config_allows_valid_reassignment(self):
        """Test that valid reassignments work."""
        config = GraphitiConfig()

        config.database = "new_database"
        config.ollama.embedding_dim = 1024

        assert config.database == "new_database"
        assert config.ollama.embedding_dim == 1024


# =============================================================================
# Integration Tests
# =============================================================================


class TestGraphitiConfigIntegration:
    """Integration tests with realistic scenarios."""

    def test_complete_openai_setup(self, monkeypatch):
        """Test complete OpenAI configuration flow."""
        monkeypatch.setenv("GRAPHITI_ENABLED", "true")
        monkeypatch.setenv("GRAPHITI_LLM_PROVIDER", "openai")
        monkeypatch.setenv("GRAPHITI_EMBEDDER_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

        config = GraphitiConfig()

        assert config.enabled is True
        assert config.llm_provider == LLMProvider.OPENAI
        assert config.embedder_provider == EmbedderProvider.OPENAI
        assert config.openai_api_key == "sk-test-123"
        assert config.get_embedding_dimension() == 1536

    def test_anthropic_llm_with_voyage_embeddings(self, monkeypatch):
        """Test Anthropic LLM + Voyage embeddings (common combo)."""
        monkeypatch.setenv("GRAPHITI_ENABLED", "true")
        monkeypatch.setenv("GRAPHITI_LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("GRAPHITI_EMBEDDER_PROVIDER", "voyage")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-123")
        monkeypatch.setenv("VOYAGE_API_KEY", "pa-voyage-123")

        config = GraphitiConfig()

        assert config.llm_provider == LLMProvider.ANTHROPIC
        assert config.embedder_provider == EmbedderProvider.VOYAGE
        assert config.get_embedding_dimension() == 1024

    def test_ollama_local_setup(self, monkeypatch):
        """Test local Ollama configuration."""
        monkeypatch.setenv("GRAPHITI_ENABLED", "true")
        monkeypatch.setenv("GRAPHITI_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("GRAPHITI_EMBEDDER_PROVIDER", "ollama")
        monkeypatch.setenv("GRAPHITI_OLLAMA__LLM_MODEL", "deepseek-r1:7b")
        monkeypatch.setenv("GRAPHITI_OLLAMA__EMBEDDING_MODEL", "nomic-embed-text")

        config = GraphitiConfig()

        assert config.llm_provider == LLMProvider.OLLAMA
        assert config.embedder_provider == EmbedderProvider.OLLAMA
        assert config.ollama.llm_model == "deepseek-r1:7b"
        assert config.ollama.embedding_model == "nomic-embed-text"
        assert config.ollama.embedding_dim == 768  # Auto-detected


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_graphiti_config():
    """Fixture providing a valid GraphitiConfig for testing."""
    return GraphitiConfig(
        enabled=True,
        llm_provider=LLMProvider.OPENAI,
        embedder_provider=EmbedderProvider.OPENAI,
        openai_api_key="sk-test-123",
        database="test_db",
    )


@pytest.fixture
def sample_graphiti_state():
    """Fixture providing a valid GraphitiState for testing."""
    return GraphitiState(
        initialized=True,
        database="test_db",
        episode_count=5,
        llm_provider="openai",
        embedder_provider="openai",
    )
