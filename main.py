"""
Main entry point for the extraction + trend pipeline.

Usage:
    # 1. Download data from openFDA
    python -m src.pipeline.ingest

    # 2. Run full pipeline (extract → embed → cluster)
    python main.py --full

    # 3. Process a single complaint
    python main.py --complaint "MRI system showed banding artifacts during cardiac sequence"

    # 4. Run just embedding + trend analysis
    python main.py --trend-only
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="Extraction + Trend Analysis Pipeline")
    parser.add_argument("--full", action="store_true", help="Run full pipeline: extract → embed → cluster")
    parser.add_argument("--extract-only", action="store_true", help="Run extraction only")
    parser.add_argument("--embed-only", action="store_true", help="Run embedding only")
    parser.add_argument("--trend-only", action="store_true", help="Run trend analysis only (needs embeddings)")
    parser.add_argument("--complaint", type=str, help="Process a single complaint narrative")
    parser.add_argument("--ingest", action="store_true", help="Download data from openFDA")
    parser.add_argument("--batch-size", type=int, default=50, help="Extraction batch size")
    parser.add_argument("--max-events", type=int, default=0, help="Max events to extract (0=all)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel extraction workers")
    parser.add_argument("--reflect", action="store_true", help="Enable self-reflection (slower but more accurate)")
    parser.add_argument("--model", type=str, default=None, help="Override LLM model string")
    parser.add_argument("--api-base", type=str, default=None, help="Custom API base URL")
    parser.add_argument("--stats", action="store_true", help="Show database statistics")
    args = parser.parse_args()

    # Model config from env or args
    model = args.model or os.getenv("EXTRACTION_MODEL", "mistral-small")
    base_url = args.api_base or os.getenv("OLLAMA_API_BASE", "http://localhost:11434")

    if args.ingest:
        from src.pipeline.ingest import run_download
        run_download()
        return

    if args.stats:
        from src.pipeline.database import get_connection, get_db_stats
        conn = get_connection()
        stats = get_db_stats(conn)
        for k, v in stats.items():
            print(f"  {k}: {v}")
        conn.close()
        return

    # For pipeline operations, import orchestrator
    from src.pipeline.orchestrator import Pipeline
    pipeline = Pipeline(model=model, base_url=base_url, num_workers=args.workers)

    try:
        if args.full:
            pipeline.run_full_pipeline(extract_batch_size=args.batch_size)

        elif args.extract_only:
            pipeline.run_extraction(batch_size=args.batch_size, reflect=args.reflect, max_events=args.max_events)

        elif args.embed_only:
            pipeline.run_embedding()

        elif args.trend_only:
            from src.embeddings.generator import EmbeddingGenerator
            embeddings, report_numbers = EmbeddingGenerator.load_embeddings()
            pipeline.run_trend_analysis(embeddings, report_numbers)

        elif args.complaint:
            result = pipeline.process_complaint(args.complaint)
            import json
            print("\n── Result ──")
            print(json.dumps(result, indent=2, default=str))

        else:
            parser.print_help()

    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
