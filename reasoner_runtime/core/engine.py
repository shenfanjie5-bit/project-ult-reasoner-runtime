from __future__ import annotations

from uuid import uuid4

from reasoner_runtime.core.models import ReasonerRequest, StructuredGenerationResult


def generate_structured(request: ReasonerRequest) -> StructuredGenerationResult:
    normalized_request = _normalize_request(request)

    # scrub: #19 will replace this pass-through with scrub_input().
    _sanitized_messages = normalized_request.messages

    # route: #18 will replace this with provider selection and fallback state.
    actual_provider = normalized_request.configured_provider
    actual_model = normalized_request.configured_model

    # call: #16 will replace this placeholder with the LiteLLM/Instructor call.
    _raw_output = ""

    # parse: #16 will parse raw model output into the requested target schema.
    parsed_result: dict[str, object] = {}

    # bundle: #17 will build the replay bundle from sanitized input and output.
    _replay_bundle = None

    return StructuredGenerationResult(
        parsed_result=parsed_result,
        actual_provider=actual_provider,
        actual_model=actual_model,
        token_usage={"prompt": 0, "completion": 0, "total": 0},
        cost_estimate=0.0,
        latency_ms=0,
    )


def _normalize_request(request: ReasonerRequest) -> ReasonerRequest:
    if not isinstance(request, ReasonerRequest):
        raise TypeError("request must be a ReasonerRequest")

    if request.max_retries < 0:
        raise ValueError("max_retries must be greater than or equal to 0")

    required_text_fields = {
        "caller_module": request.caller_module,
        "target_schema": request.target_schema,
        "configured_provider": request.configured_provider,
        "configured_model": request.configured_model,
    }
    missing_fields = [
        field_name
        for field_name, value in required_text_fields.items()
        if not value.strip()
    ]
    if missing_fields:
        joined_fields = ", ".join(missing_fields)
        raise ValueError(f"required request fields cannot be empty: {joined_fields}")

    if request.request_id.strip():
        return request

    return request.model_copy(update={"request_id": str(uuid4())})
