"""Tests for model_registry.py's static capability metadata resolver."""
import pytest

from model_registry import get_model_metadata, MODEL_REGISTRY, DEFAULT_METADATA


class TestGetModelMetadata:
    @pytest.mark.parametrize("active_model,registry_key", [
        ("Groq_Llama_3", "groq"),
        ("OpenAI_GPT_4o", "openai"),
        ("Anthropic_Claude_3", "anthropic"),
        ("Gemini_Flash", "gemini"),
        ("Ollama_Local", "ollama"),
        ("LlamaCpp_Local", "llamacpp"),
    ])
    def test_known_active_models_resolve_to_registry(self, active_model, registry_key):
        assert get_model_metadata(active_model) == MODEL_REGISTRY[registry_key]

    def test_custom_local_resolves_to_ollama_metadata(self):
        # Custom provider profiles have no fixed identity — is_local classifies them.
        assert get_model_metadata("Custom", is_local=True) == MODEL_REGISTRY["ollama"]

    def test_custom_cloud_resolves_to_default(self):
        assert get_model_metadata("Custom", is_local=False) == DEFAULT_METADATA

    def test_unknown_model_resolves_to_default(self):
        assert get_model_metadata("SomethingThatDoesntExist") == DEFAULT_METADATA

    def test_groq_safe_ceiling_far_below_its_advertised_context_window(self):
        # The whole point of a separate safe_request_ceiling: Groq's usable
        # throughput is much smaller than the model card's context window.
        groq = MODEL_REGISTRY["groq"]
        assert groq["safe_request_ceiling"] < groq["context_window"] / 2

    def test_local_providers_use_full_context_window_as_ceiling(self):
        for key in ("ollama", "llamacpp"):
            meta = MODEL_REGISTRY[key]
            assert meta["safe_request_ceiling"] == meta["context_window"]
            assert meta["local"] is True
