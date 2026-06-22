"""Model-callable tools and the tool-calling engine.

This package is the home for everything related to **tool use** by the agents:

- ``tool_loop`` — the ``AnthropicToolClient`` engine (drives the model→tool→model
  loop over the ``claude`` CLI) and the ``ToolSpec`` contract.
- ``quality_tools`` — the deterministic ``QualityAnalyticsToolbox`` (offline
  analytics over the MAUDE/recall archive).
- ``agent_tools`` — builders that wrap deterministic Python functions as
  ``ToolSpec`` objects the model can call (quality analytics, retrieval, trend).

Contributor guide: to expose a new capability to an agent, add a deterministic
function (here or in a domain module), wrap it as a ``ToolSpec`` via a builder in
``agent_tools``, and register that builder where the owning agent assembles its
tools. Keep the genuine decision arguments in the schema and bind runtime context
(archives, product codes) by closure so the model never has to invent it.
"""
