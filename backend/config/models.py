"""Canonical model identifiers for each agent.

IDs must match GET https://api.vultrinference.com/v1/models exactly.

The RAISE serverless inference subscription exposes the full Vultr chat
catalog (not a single pinned model). Always pass an explicit catalog id.

Legacy docs / project-plan still mention "kimi-k2-instruct". That string is
NOT in the live catalog; requesting it silently falls back to
MiniMaxAI/MiniMax-M2.7. Never use that alias.
"""

from __future__ import annotations

from typing import Final

# Planner/Orchestrator — must support tool calling (Modeling Tool).
# Live Kimi successor to the dead "kimi-k2-instruct" alias; tool calling
# confirmed with requested_model == reported_model.
PLANNER_MODEL: Final[str] = "moonshotai/Kimi-K2.6"

# Also confirmed for tool calling (what the dead kimi alias falls back to).
# Prefer PLANNER_MODEL; keep as explicit fallback if Kimi is flaky in demo.
PLANNER_MODEL_FALLBACK: Final[str] = "MiniMaxAI/MiniMax-M2.7"

# Retrieval agents (Vultr VultronRetriever)
INTERNAL_RETRIEVAL_MODEL: Final[str] = "vultr/VultronRetrieverCore-Qwen3.5-4.5B"
BENCHMARK_RETRIEVAL_MODEL: Final[str] = "vultr/VultronRetrieverCore-Qwen3.5-4.5B"

# Explainability — NVIDIA free catalog (not Vultr)
EXPLAINABILITY_MODEL: Final[str] = "nvidia/nemotron-3-ultra-550b-a55b"
# Plan §3b fallback when NVIDIA is flaky/rate-limited
EXPLAINABILITY_FALLBACK_MODEL: Final[str] = "zai-org/GLM-5.2-FP8"

# Report Agent — memo assembly on Vultr (plan: Nemotron-3-Nano-Omni or MiniMax)
# MiniMax preferred here: Nano-Omni often spends the budget on reasoning and
# truncates the memo body under the REPORT max_tokens cap.
REPORT_MODEL: Final[str] = "MiniMaxAI/MiniMax-M2.7"

# Known-dead alias (do not use) — silent fallback to MiniMaxAI/MiniMax-M2.7
LEGACY_KIMI_ALIAS: Final[str] = "kimi-k2-instruct"
