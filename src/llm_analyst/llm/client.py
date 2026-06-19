"""LLMClient protocol and AnthropicLLMClient implementation.

The protocol defines a single method — create_message — so both the planner and
the composer (Phase 3+) can call the same interface with different model values.
One method keeps the protocol minimal (engineering-principles §6: no layer unless
used in ≥3 places). The planner passes its model constant; Phase 3 composer
passes COMPOSER_MODEL.

Sync-only in Phase 2. If Phase 5 needs async, add AsyncLLMClient as a separate
protocol rather than mutating this interface.
"""

from __future__ import annotations

import os
from typing import Any, Protocol, runtime_checkable

import anthropic

# Model constants: the only place model IDs appear in this codebase.
# Use the canonical alias form (no date suffix) so routing follows the latest
# supported snapshot of that model series. Date-suffixed IDs pin to a specific
# sub-release that Anthropic may retire without notice.
# Verify current aliases: https://docs.anthropic.com/en/docs/about-claude/models
# Haiku for planning: low-latency structured output, no prose needed.
# Sonnet reserved for Phase 3 answer composition where prose quality matters.
PLANNER_MODEL = "claude-haiku-4-5"
COMPOSER_MODEL = "claude-sonnet-4-6"


@runtime_checkable
class LLMClient(Protocol):
    """Minimal protocol any LLM backend must satisfy.

    A single method keeps the surface injectable and testable. Both the planner
    and the Phase 3 composer call create_message with their own model constant,
    keeping model routing inside each caller rather than inside the protocol.
    """

    def create_message(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Return a Message-shaped dict with at minimum 'stop_reason' and 'content'."""
        ...


class AnthropicLLMClient:
    """Thin wrapper around anthropic.Anthropic that satisfies LLMClient.

    Raises EnvironmentError at construction time if ANTHROPIC_API_KEY is absent
    and no api_key is passed — fail loud at startup, not at first API call.
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise OSError(
                "ANTHROPIC_API_KEY is not set and no api_key was passed to AnthropicLLMClient. "
                "Export the key or pass it explicitly."
            )
        self._client = anthropic.Anthropic(api_key=resolved_key)

    def create_message(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: dict[str, Any],
        max_tokens: int,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        message = self._client.messages.create(
            model=model,
            system=system,
            messages=messages,
            tools=tools,  # type: ignore[arg-type]
            tool_choice=tool_choice,  # type: ignore[arg-type]
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return message.model_dump()
