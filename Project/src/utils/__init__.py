"""Generic infrastructure helpers (no domain/agent logic).

Home for cross-cutting utilities: LLM clients (``llm_client``,
``custom_anthropic_client``), prompt loading (``prompt_store``), data loading
(``data_loader``), persistence (``storage``), and document IO (``docx_io``).
Model-callable tools and the tool-calling engine live in ``src.tools``; agents
live in ``src.agents``.
"""
