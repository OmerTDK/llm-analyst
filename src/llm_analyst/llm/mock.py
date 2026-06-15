"""MockLLMClient: deterministic injectable LLMClient for CI.

Keyed on the last user message content. Returns pre-configured tool_use
responses without any network call. Satisfies LLMClient at runtime (verified
by isinstance check in tests).

No cassette infrastructure needed: the golden-plan JSON fixtures provide a
deterministic fixture set that maps question text to expected plan input. This
avoids the maintenance cliff of VCR cassettes (which embed full HTTP
request/response pairs and break on SDK version bumps).
"""

from __future__ import annotations

from typing import Any


class MockLLMClient:
    """Injectable LLMClient that returns pre-configured tool_use responses.

    plan_responses maps normalized question text to the raw tool_input dict
    the planner should receive. If the question is not in the map, raises
    ValueError so tests fail clearly rather than silently returning wrong data.
    """

    def __init__(self, plan_responses: dict[str, dict[str, Any]]) -> None:
        self._plan_responses = plan_responses

    def create_message(
        self,
        *,
        messages: list[dict[str, Any]],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        user_message = messages[-1]["content"]
        if user_message not in self._plan_responses:
            raise ValueError(
                f"MockLLMClient has no fixture response for question: {user_message!r}. "
                f"Add it to plan_responses or load the matching golden-plan fixture."
            )
        tool_input = self._plan_responses[user_message]
        return {
            "stop_reason": "tool_use",
            "content": [
                {
                    "type": "tool_use",
                    "id": "mock_toolu_01",
                    "name": "plan_query",
                    "input": tool_input,
                }
            ],
        }
