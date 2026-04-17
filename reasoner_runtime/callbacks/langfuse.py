from __future__ import annotations

from typing import Any

from reasoner_runtime.callbacks.base import (
    CallbackContext,
    CallbackError,
    CallbackSuccess,
)
from reasoner_runtime.scrub.rules import scrub_text


_MAX_ERROR_MESSAGE_CHARS = 500


class LangfuseCallbackBackend:
    def __init__(
        self,
        client: Any | None = None,
        *,
        host: str | None = None,
        trace_name: str = "reasoner.llm",
    ) -> None:
        self._client = client
        self.host = host
        self.trace_name = trace_name

    def on_start(self, context: CallbackContext) -> None:
        self._emit_event(
            "reasoner.llm.start",
            _context_metadata(context),
        )

    def on_success(
        self,
        context: CallbackContext,
        success: CallbackSuccess,
    ) -> None:
        self._emit_event(
            "reasoner.llm.success",
            {
                **_context_metadata(context),
                **_success_metadata(success),
            },
        )

    def on_error(self, context: CallbackContext, error: CallbackError) -> None:
        self._emit_event(
            "reasoner.llm.error",
            {
                **_context_metadata(context),
                **_error_metadata(error),
            },
        )

    def _emit_event(self, name: str, metadata: dict[str, Any]) -> None:
        try:
            client = self._get_client()
            if _emit_on_target(client, name, metadata):
                return

            trace_method = getattr(client, "trace", None)
            if not callable(trace_method):
                return

            trace = _build_trace(trace_method, self.trace_name)
            _emit_on_target(trace, name, metadata)
        except Exception:
            return

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = _build_default_client(self.host)
        return self._client


def _build_default_client(host: str | None) -> Any:
    try:
        from langfuse import Langfuse
    except ImportError as error:
        raise RuntimeError(
            "Langfuse callback backend requires the optional 'langfuse' package "
            "when no client is injected"
        ) from error

    if host:
        return Langfuse(host=host)
    return Langfuse()


def _context_metadata(context: CallbackContext) -> dict[str, Any]:
    return {
        "request_id": context.request_id,
        "caller_module": context.caller_module,
        "target_schema": context.target_schema,
        "provider": context.provider,
        "model": context.model,
    }


def _success_metadata(success: CallbackSuccess) -> dict[str, Any]:
    return {
        "token_usage": dict(success.token_usage),
        "cost_estimate": success.cost_estimate,
        "latency_ms": success.latency_ms,
        "fallback_path": list(success.fallback_path),
        "retry_count": success.retry_count,
        "failure_class": success.failure_class,
    }


def _error_metadata(error: CallbackError) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "error_type": error.error_type,
        "error_message": _truncate(scrub_text(error.error_message).strip()),
        "failure_class": error.failure_class,
    }
    if error.latency_ms is not None:
        metadata["latency_ms"] = error.latency_ms
    return metadata


def _emit_on_target(target: Any, name: str, metadata: dict[str, Any]) -> bool:
    event_method = getattr(target, "event", None)
    if not callable(event_method):
        return False

    try:
        event_method(name=name, metadata=metadata)
    except TypeError:
        event_method(name, metadata=metadata)
    return True


def _build_trace(trace_method: Any, trace_name: str) -> Any:
    try:
        return trace_method(name=trace_name)
    except TypeError:
        return trace_method(trace_name)


def _truncate(value: str) -> str:
    if len(value) <= _MAX_ERROR_MESSAGE_CHARS:
        return value
    return value[: _MAX_ERROR_MESSAGE_CHARS - 3].rstrip() + "..."


__all__ = ["LangfuseCallbackBackend"]
