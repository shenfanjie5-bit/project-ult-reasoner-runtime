from __future__ import annotations

import sys
from pathlib import Path


def ensure_contracts_importable() -> None:
    try:
        import contracts  # noqa: F401
    except ModuleNotFoundError as error:
        if error.name != "contracts":
            raise
        sibling_contracts_src = (
            Path(__file__).resolve().parents[2] / "contracts" / "src"
        )
        if not sibling_contracts_src.exists():
            raise ModuleNotFoundError(
                "project-ult-contracts is required but the contracts package "
                "is not installed and ../contracts/src was not found"
            ) from error

        sys.path.insert(0, str(sibling_contracts_src))
        import contracts  # noqa: F401
