import argparse
import json
from dataclasses import asdict

from src.pipeline.orchestrator import SignalWorkflowOrchestrator, WorkflowConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LangGraph 5-agent regulatory workflow")
    parser.add_argument("--complaints-per-code", type=int, default=6)
    parser.add_argument("--max-events-per-code", type=int, default=250)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    orchestrator = SignalWorkflowOrchestrator(
        config=WorkflowConfig(
            complaints_per_code=args.complaints_per_code,
            max_events_per_code=args.max_events_per_code,
            random_seed=args.seed,
        )
    )
    result = orchestrator.run()
    print(json.dumps(asdict(result), indent=2, default=str))


if __name__ == "__main__":
    main()
