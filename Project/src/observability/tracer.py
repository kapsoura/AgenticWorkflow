import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class TraceLogger:
    def __init__(self, trace_id: str, logs_dir: Path):
        self.trace_id = trace_id
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.logs_dir / f"{trace_id}.jsonl"
        # In-memory copy of every emitted record so callers (e.g. the web UI)
        # can replay the exact sequence of agent activity for validation.
        self.events: list[Dict[str, Any]] = []

    def log(
        self,
        agent: str,
        event: str,
        latency_ms: Optional[float] = None,
        gate_result: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "trace_id": self.trace_id,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "agent": agent,
            "event": event,
            "latency_ms": latency_ms,
            "tool_calls": [],
            "input_tokens": None,
            "output_tokens": None,
            "model": None,
            "gate_result": gate_result,
            "error": error,
            "metadata": metadata or {},
        }
        self.events.append(record)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
