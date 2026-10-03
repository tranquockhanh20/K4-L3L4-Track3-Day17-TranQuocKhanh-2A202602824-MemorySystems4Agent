from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for the memory systems lab."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def _resolve_api_key(provider: str) -> str | None:
    norm = normalize_provider(provider)
    if norm in ("openai", "custom"):
        return os.getenv("OPENAI_API_KEY") or os.getenv("CUSTOM_API_KEY")
    elif norm == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    elif norm == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    elif norm == "openrouter":
        return os.getenv("OPENROUTER_API_KEY")
    return None


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables and return a populated LabConfig instance."""
    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    env_path = root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    data_dir = root / "data"
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "profiles").mkdir(parents=True, exist_ok=True)

    compact_threshold = int(os.getenv("COMPACT_THRESHOLD_TOKENS", "800"))
    compact_keep = int(os.getenv("COMPACT_KEEP_MESSAGES", "4"))

    main_provider = os.getenv("LLM_PROVIDER", "openai")
    main_model_name = os.getenv("LLM_MODEL", "gpt-4o-mini")
    main_temp = float(os.getenv("LLM_TEMPERATURE", "0.0"))
    main_base_url = os.getenv("CUSTOM_BASE_URL") or os.getenv("OLLAMA_BASE_URL")
    main_api_key = _resolve_api_key(main_provider)

    model_config = ProviderConfig(
        provider=main_provider,
        model_name=main_model_name,
        temperature=main_temp,
        api_key=main_api_key,
        base_url=main_base_url,
    )

    judge_provider = os.getenv("JUDGE_PROVIDER", main_provider)
    judge_model_name = os.getenv("JUDGE_MODEL", main_model_name)
    judge_temp = float(os.getenv("JUDGE_TEMPERATURE", "0.0"))
    judge_base_url = os.getenv("JUDGE_BASE_URL", main_base_url)
    judge_api_key = _resolve_api_key(judge_provider) or main_api_key

    judge_config = ProviderConfig(
        provider=judge_provider,
        model_name=judge_model_name,
        temperature=judge_temp,
        api_key=judge_api_key,
        base_url=judge_base_url,
    )

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=compact_threshold,
        compact_keep_messages=compact_keep,
        model=model_config,
        judge_model=judge_config,
    )
