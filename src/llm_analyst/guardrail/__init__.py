"""Guardrail layer: scope classification and governance enforcement.

GuardedAnalyst is the single public entrypoint for the analyst system.
The raw Analyst class is not re-exported from this package — callers must
go through GuardedAnalyst to obtain an answer.

Public API:
  GuardedAnalyst.ask(question) -> AnalystAnswer | RefusalResponse
  RefusalResponse: structured refusal with plain-language explanation
"""

from .guarded_analyst import GuardedAnalyst
from .models import RefusalResponse

__all__ = ["GuardedAnalyst", "RefusalResponse"]
