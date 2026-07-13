"""Canonical model identifiers for each agent.

IDs must match GET https://api.vultrinference.com/v1/models exactly.

The RAISE serverless inference subscription exposes the full Vultr chat
catalog (not a single pinned model). Always pass an explicit catalog id.

WARNING: the legacy alias "kimi-k2-instruct" is NOT in the live catalog;
requesting it silently falls back to MiniMaxAI/MiniMax-M2.7. Never use it.
"""

from __future__ import annotations

from typing import Final

# Claim validation (retrieval stage) — must support tool calling.
# Tool calling confirmed with requested_model == reported_model.
CLAIM_VALIDATION_MODEL: Final[str] = "moonshotai/Kimi-K2.6"

# Also confirmed for tool calling. Explicit fallback if Kimi is flaky.
CLAIM_VALIDATION_MODEL_FALLBACK: Final[str] = "MiniMaxAI/MiniMax-M2.7"

# Retrieval agents (Vultr VultronRetriever — /v1/rerank only)
INTERNAL_RETRIEVAL_MODEL: Final[str] = "vultr/VultronRetrieverCore-Qwen3.5-4.5B"
BENCHMARK_RETRIEVAL_MODEL: Final[str] = "vultr/VultronRetrieverCore-Qwen3.5-4.5B"

# Explainability — NVIDIA free catalog (not Vultr)
EXPLAINABILITY_MODEL: Final[str] = "nvidia/nemotron-3-ultra-550b-a55b"
# Vultr fallback when NVIDIA is flaky/rate-limited
EXPLAINABILITY_FALLBACK_MODEL: Final[str] = "zai-org/GLM-5.2-FP8"

# Report Agent — recommendation generation on Vultr.
# MiniMax preferred: Nemotron-Nano-Omni often spends the budget on reasoning
# and truncates the output under the REPORT max_tokens cap.
REPORT_MODEL: Final[str] = "MiniMaxAI/MiniMax-M2.7"
