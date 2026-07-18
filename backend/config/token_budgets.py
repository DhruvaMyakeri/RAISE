"""Per-agent max_tokens budgets (cost-control convention).

Short/structured agents stay in the 500-2500 range. Explainability may use a
higher budget because that output is reader-facing and benefits from deeper
reasoning. Never default every LLM call to a high max_tokens value.

Model identifiers live in config.models (not here).
"""

from __future__ import annotations

from typing import Final, TypedDict


class AgentBudget(TypedDict, total=False):
    max_tokens: int
    # NVIDIA Explainability only — passed via extra_body
    reasoning_budget: int


# Claim validation (agents/retrieval.py) — the prompt includes benchmark
# context and the model reasons before emitting the tool output.
CLAIM_VALIDATION: Final[AgentBudget] = {"max_tokens": 2500}

# Intake extraction (agents/intake.py) — document -> structured profile fields.
# The document itself is in the prompt; output is a compact tool call.
INTAKE_EXTRACTION: Final[AgentBudget] = {"max_tokens": 2000}

# Explainability (nemotron on NVIDIA) — deeper reasoning allowed
EXPLAINABILITY: Final[AgentBudget] = {
    "max_tokens": 16384,
    "reasoning_budget": 16384,
}
# Vultr fallback for Explainability — keep moderate
EXPLAINABILITY_FALLBACK: Final[AgentBudget] = {"max_tokens": 1200}

# Report Agent — recommendation from already-computed content (A vs B).
# MiniMax reasoning overhead consumes ~600-800 tokens before the tool-call
# arguments; the recommendation itself needs ~800-1000.
REPORT: Final[AgentBudget] = {"max_tokens": 2000}

# Smoke / connectivity tests only — keep tiny
SMOKE_TEST: Final[AgentBudget] = {"max_tokens": 500}
SMOKE_TEST_NVIDIA: Final[AgentBudget] = {
    "max_tokens": 256,
    "reasoning_budget": 256,
}
