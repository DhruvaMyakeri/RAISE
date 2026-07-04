"""Per-agent max_tokens budgets (cost-control convention).

Short/structured agents stay in the 500–1000 range.
Explainability may use a higher budget (project-plan §3c) because that
output is judge-facing and benefits from deeper reasoning.

Never default every LLM call to a high max_tokens value.

Model identifiers live in config.models (not here). Planner uses
moonshotai/Kimi-K2.6 (fallback: MiniMaxAI/MiniMax-M2.7). Never use the
dead alias kimi-k2-instruct — it silently routes to MiniMax.
"""

from __future__ import annotations

from typing import Final, TypedDict


class AgentBudget(TypedDict, total=False):
    max_tokens: int
    # NVIDIA Explainability only — passed via extra_body
    reasoning_budget: int


# Planner / Orchestrator (Kimi-K2.6) — classification, tool trigger
# Top of 500–1000 band: model may spend tokens on reasoning before content.
PLANNER: Final[AgentBudget] = {"max_tokens": 1000}

# Internal + Benchmark Retrieval (VultronRetriever) — structured extracts / flags
INTERNAL_RETRIEVAL: Final[AgentBudget] = {"max_tokens": 800}
BENCHMARK_RETRIEVAL: Final[AgentBudget] = {"max_tokens": 800}

# Explainability (nemotron-3-ultra on NVIDIA) — deeper reasoning allowed
EXPLAINABILITY: Final[AgentBudget] = {
    "max_tokens": 16384,
    "reasoning_budget": 16384,
}
# Vultr fallback for Explainability (plan §3b) — keep moderate
EXPLAINABILITY_FALLBACK: Final[AgentBudget] = {"max_tokens": 1200}

# Report Agent — memo assembly from already-computed content (A vs B memo).
# MiniMax reasoning overhead consumes ~600-800 tokens before the tool-call
# arguments; the memo body itself needs ~800-1000. 2000 covers both without
# approaching the Explainability budget tier.
REPORT: Final[AgentBudget] = {"max_tokens": 2000}

# Claim validation (retrieval.py) — needs more room than Planner since the
# prompt includes benchmark context and the model reasons before tool output.
CLAIM_VALIDATION: Final[AgentBudget] = {"max_tokens": 2500}

# Smoke / connectivity tests only — keep tiny
SMOKE_TEST: Final[AgentBudget] = {"max_tokens": 500}
SMOKE_TEST_NVIDIA: Final[AgentBudget] = {
    "max_tokens": 256,
    "reasoning_budget": 256,
}
