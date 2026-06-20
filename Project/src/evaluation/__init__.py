"""Evaluation harness for the signal-intelligence pipeline (US-16).

Runs the gold benchmark (US-05) through the real pipeline and scores the
outputs against hand-labeled expectations. The package is dependency-free
beyond the standard library and the pipeline itself:

- ``metrics``  pure scoring functions (set P/R/F1, precision@k, recall, means).
- ``gold``     gold-case dataclass + JSON loader.
- ``harness``  drives ``SignalService`` over the gold cases, scores each, and
               aggregates an ``EvaluationReport`` (JSON + Markdown).
- ``run_eval`` ``python -m src.evaluation.run_eval`` command-line entry point.

Semantic metrics (category accuracy, key-issue recall, risk bucketing) are only
meaningful when an LLM backend is available; structural metrics (prompt-injection
rejection, retrieval grounding, schema validity, citation hallucination) run in
every mode. When no LLM is configured the harness reports the degraded mode
explicitly instead of failing.
"""
