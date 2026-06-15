"""llm-analyst: natural-language analytics over a governed semantic layer.

Public entrypoints for Phase 3+:
  GuardedAnalyst — the only public path to an answer; enforces scope and governance.
  RefusalResponse — structured refusal for out-of-scope or governance-violating questions.

The raw Analyst class is intentionally not exported here. All callers must go
through GuardedAnalyst to ensure the scope classifier and governance boundary
are always applied.
"""

from llm_analyst.guardrail import GuardedAnalyst, RefusalResponse

__all__ = ["GuardedAnalyst", "RefusalResponse"]
