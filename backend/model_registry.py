"""Static per-provider model capability metadata.

This is the missing prerequisite for token-budgeted context assembly
(context_manager.py) and any future capability-based routing. It is
deliberately NOT a live/dynamic registry — provider capabilities (context
window, vision, tool-calling) don't change at runtime, only which model
string a user has picked within a provider does (see settings_manager.py's
per-provider *_model fields for that).

`safe_request_ceiling` is intentionally far below `context_window` for cloud
providers, especially Groq: the model card's advertised window is not the
same as what a request can actually push through in practice, which is
exactly what brain.py's existing GROQ_FALLBACK_CHAIN/429-rotation logic
already fights. Local providers (Ollama/LlamaCpp) have no such external
rate/size ceiling, so their safe ceiling equals their context window.
"""

MODEL_REGISTRY: dict[str, dict] = {
    "groq": {
        "context_window": 131072,
        "safe_request_ceiling": 24000,
        "vision": False,
        "tool_calling": True,
        "local": False,
    },
    "openai": {
        "context_window": 128000,
        "safe_request_ceiling": 100000,
        "vision": True,
        "tool_calling": True,
        "local": False,
    },
    "anthropic": {
        "context_window": 200000,
        "safe_request_ceiling": 150000,
        "vision": True,
        "tool_calling": True,
        "local": False,
    },
    "gemini": {
        "context_window": 1000000,
        "safe_request_ceiling": 100000,
        "vision": True,
        "tool_calling": False,
        "local": False,
    },
    "ollama": {
        "context_window": 8192,
        "safe_request_ceiling": 8192,
        "vision": False,
        "tool_calling": False,
        "local": True,
    },
    "llamacpp": {
        "context_window": 8192,
        "safe_request_ceiling": 8192,
        "vision": False,
        "tool_calling": False,
        "local": True,
    },
}

DEFAULT_METADATA: dict = {
    "context_window": 8000,
    "safe_request_ceiling": 8000,
    "vision": False,
    "tool_calling": False,
    "local": False,
}

# Maps brain.py's routing key (settings["active_model"]) to a MODEL_REGISTRY key.
_ACTIVE_MODEL_TO_REGISTRY_KEY = {
    "Groq_Llama_3": "groq",
    "OpenAI_GPT_4o": "openai",
    "Anthropic_Claude_3": "anthropic",
    "Gemini_Flash": "gemini",
    "Ollama_Local": "ollama",
    "LlamaCpp_Local": "llamacpp",
}


def get_model_metadata(active_model: str, is_local: bool = False) -> dict:
    """Resolves capability metadata for the currently active routing key.

    `Custom` provider profiles have no fixed provider identity — they're
    classified purely by `is_local` (caller should pass brain.py's
    `_is_local_provider(active_model, settings)` result), since a
    self-hosted OpenAI-compatible server has no external rate ceiling but
    an unknown one pointed at a cloud host does.
    """
    registry_key = _ACTIVE_MODEL_TO_REGISTRY_KEY.get(active_model)
    if registry_key:
        return MODEL_REGISTRY[registry_key]
    if is_local:
        return MODEL_REGISTRY["ollama"]
    return DEFAULT_METADATA
