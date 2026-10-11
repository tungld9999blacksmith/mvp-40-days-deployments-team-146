"""Agent-level evaluation harness for the EV Care AI agent.

This package complements the RAG-retrieval evaluation under
``backend/tests/test_agents/test_rag/evaluation/`` by adding the agent-level
and statistical metrics described in
``docs/specs/ai-agent/ai-eval-testing-strategy.spec.md`` (D8):

- metrics.stats       : confidence intervals (Wilson, bootstrap) and A/B tests.
- metrics.text        : exact-match, token-F1, ROUGE-L (+ optional BLEU/BERTScore).
- metrics.tool_calling: tool-selection accuracy and argument F1.
- metrics.trajectory  : ReAct trajectory match, in-order recall, efficiency.

All core metrics are dependency-light (standard library only). Heavier,
optional metrics (BLEU/BERTScore/RAGAS/DeepEval) are imported lazily and guarded
so the suite runs without them.
"""

__all__ = ["metrics"]
