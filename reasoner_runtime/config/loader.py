from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter

from reasoner_runtime.config.models import (
    CallbackProfile,
    ProviderProfile,
    ScrubRuleSet,
)


def _load_yaml(config_path: Path) -> Any:
    with config_path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file)


def load_provider_profiles(config_path: Path) -> list[ProviderProfile]:
    data = _load_yaml(config_path)
    if isinstance(data, dict) and "providers" in data:
        data = data["providers"]
    return TypeAdapter(list[ProviderProfile]).validate_python(data)


def load_scrub_rules(config_path: Path) -> ScrubRuleSet:
    data = _load_yaml(config_path)
    if isinstance(data, dict) and "scrub" in data:
        data = data["scrub"]
    return ScrubRuleSet.model_validate(data)


def load_callback_profile(config_path: Path) -> CallbackProfile:
    data = _load_yaml(config_path)
    if isinstance(data, dict) and "callback" in data:
        data = data["callback"]
    return CallbackProfile.model_validate(data)
