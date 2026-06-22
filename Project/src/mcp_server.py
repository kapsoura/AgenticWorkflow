from dataclasses import asdict

from src.pipeline.orchestrator import SignalWorkflowOrchestrator, WorkflowConfig

try:
    from mcp.server.fastmcp import FastMCP
except Exception:  # pragma: no cover
    FastMCP = None


if FastMCP is not None:
    mcp = FastMCP("multi-agent-quality-intelligence")

    @mcp.tool()
    def run_signal_workflow(
        complaints_per_code: int = 6,
        max_events_per_code: int = 250,
        seed: int = 42,
    ) -> dict:
        """Run the 5-agent workflow and return run metadata."""
        orchestrator = SignalWorkflowOrchestrator(
            config=WorkflowConfig(
                complaints_per_code=complaints_per_code,
                max_events_per_code=max_events_per_code,
                random_seed=seed,
            )
        )
        return asdict(orchestrator.run())


def main() -> None:
    if FastMCP is None:
        raise RuntimeError("mcp package is not installed. Install dependencies first.")
    mcp.run()


if __name__ == "__main__":
    main()
