"""Agent modules for the regulatory signal workflow.

One agent per file. Each agent owns a single pipeline component and exposes a
plain method the orchestrator/LangGraph flow calls. Current agents:

- ``extraction`` — single-pass structured extraction (L1 Augmented LLM)
- ``retrieval`` — evidence retrieval / Graph RAG (L1->L2)
- ``risk_analysis`` — ISO 14971 risk + CAPA (L1, two-pass self-critique)
- ``report_generation`` — report assembly (L2 Evaluator-Optimizer)
- ``report_sections`` — section blueprints + builders used by the report agent
- ``orchestration`` — fixed-pipeline orchestrator that drives sub-agents
- ``archive_trend`` — non-LLM trend/similarity summariser
- ``cluster_assignment`` — non-LLM HDBSCAN cluster assignment

Contributor guide: to add an agent, create ``your_agent.py`` here exposing one
class with a clear entry method, keep model-callable tools in ``src.tools``, and
generic helpers in ``src.utils``. Wire it into the flow via ``src.pipeline``.
"""
