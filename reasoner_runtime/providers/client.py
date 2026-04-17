from __future__ import annotations

from typing import Any

from reasoner_runtime.config.models import ProviderProfile


def build_client(profile: ProviderProfile, max_retries: int) -> Any:
    if max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    return {
        "profile": profile,
        "max_retries": max_retries,
    }
