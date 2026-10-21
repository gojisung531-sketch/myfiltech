from .base import LLMError, LLMProvider


def get_provider_class(provider: str) -> type[LLMProvider]:
    if provider == "ANTHROPIC":
        from .anthropic import AnthropicProvider

        return AnthropicProvider
    if provider == "OPENAI":
        from .openai import OpenAIProvider

        return OpenAIProvider
    if provider == "GEMINI":
        from .gemini import GeminiProvider

        return GeminiProvider
    raise ValueError(f"Unknown LLM provider: {provider}")


__all__ = ["LLMError", "LLMProvider", "get_provider_class"]
