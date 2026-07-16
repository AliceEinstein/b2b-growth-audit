"""Provider stub for a future execution mode.

The artifact/task protocol is the stable boundary. A future OpenAI,
Anthropic, Codex CLI, Claude Code SDK, or LiteLLM adapter can implement this
interface without changing the workflow or output contracts.
"""
from __future__ import annotations

from typing import Any, Dict, Protocol


class ProviderNotConfigured(RuntimeError):
    """Raised when provider-driven execution is requested but not installed."""


class ProviderExecutor(Protocol):
    def execute(self, task_packet: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task and return a structured artifact document."""


def unavailable_provider(task_packet: Dict[str, Any]) -> Dict[str, Any]:
    raise ProviderNotConfigured(
        "Provider-driven mode is not part of V1. Use the generated task packet "
        "with Codex or Claude Code, or install a future provider adapter."
    )
