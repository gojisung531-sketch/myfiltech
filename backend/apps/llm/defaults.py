"""Seed data for LLM model options (specs/07-llm-integration.md §3).

Model IDs live only here as seed data; admins can add/edit them in the UI.
"""

from .models import LLMModelOption, LLMProviderConfig, LLMSettings, PromptTemplate, Provider
from .prompt_defaults import COMMON_SYSTEM, PROMPTS

MODEL_OPTION_DEFAULTS = [
    # provider, model_id, display_name, supports_pdf_input, is_default
    (Provider.ANTHROPIC, "claude-opus-5-5", "Claude Opus 5.5", True, True),
    (Provider.ANTHROPIC, "claude-fable-5-1", "Claude Fable 5.1", True, False),
    (Provider.ANTHROPIC, "claude-sonnet-5-5", "Claude Sonnet 5.5", True, False),
    (Provider.ANTHROPIC, "claude-haiku-4-5-20251001", "Claude Haiku 4.5", True, False),
    (Provider.OPENAI, "gpt-6-astra", "GPT-6 Astra", False, True),
    (Provider.OPENAI, "gpt-6.1-sol", "GPT-6.1 Sol", False, False),
    (Provider.OPENAI, "gpt-6-luna", "GPT-6 Luna", False, False),
    (Provider.GEMINI, "gemini-3.8-flash", "Gemini 3.8 Flash", True, True),
    (Provider.GEMINI, "gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite", True, False),
]


def prompt_fields(default: dict) -> dict:
    return {
        "name": default["name"],
        "description": default["description"],
        "system_prompt": COMMON_SYSTEM,
        "user_prompt_template": default["user_prompt_template"],
        "output_schema": default["output_schema"],
    }


SEED_NOTE = "기본값"


def seed_prompts() -> int:
    """Create missing prompts; refresh untouched seeds when the defaults change.

    A seed is untouched when its key has only version 1 and the note is still the seed
    note (specs/07 §4.3). Admin-edited prompts are never modified.
    """
    changed = 0
    for default in PROMPTS:
        versions = list(PromptTemplate.objects.filter(key=default["key"]))
        fields = prompt_fields(default)
        if not versions:
            PromptTemplate.objects.create(
                key=default["key"], version=1, is_active=True, notes=SEED_NOTE, **fields
            )
            changed += 1
            continue
        seed = versions[0]
        untouched = len(versions) == 1 and seed.version == 1 and seed.notes == SEED_NOTE
        if untouched and any(getattr(seed, k) != v for k, v in fields.items()):
            for name, value in fields.items():
                setattr(seed, name, value)
            seed.save()
            changed += 1
    return changed


def seed_llm_defaults() -> None:
    """Create missing providers, model options, prompts and the settings row. Never overwrites."""
    for provider in Provider.values:
        LLMProviderConfig.objects.get_or_create(provider=provider)

    has_default = set(
        LLMModelOption.objects.filter(is_default=True).values_list("provider", flat=True)
    )
    for order, (provider, model_id, name, pdf, is_default) in enumerate(MODEL_OPTION_DEFAULTS):
        if LLMModelOption.objects.filter(provider=provider, model_id=model_id).exists():
            continue
        LLMModelOption.objects.create(
            provider=provider,
            model_id=model_id,
            display_name=name,
            supports_pdf_input=pdf,
            is_default=is_default and provider not in has_default,
            order=order,
        )

    seed_prompts()

    settings_row = LLMSettings.load()
    if settings_row.active_model is None:
        settings_row.active_model = LLMModelOption.objects.filter(
            provider=settings_row.active_provider, is_default=True
        ).first()
        settings_row.save()
