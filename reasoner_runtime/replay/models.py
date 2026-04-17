from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ReplayBundle(BaseModel):
    sanitized_input: str
    input_hash: str
    raw_output: str
    parsed_result: dict[str, Any]
    output_hash: str
    llm_lineage: dict[str, Any]
