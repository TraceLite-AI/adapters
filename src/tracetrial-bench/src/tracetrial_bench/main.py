"""CLI entry point for the Harbor TraceTrial-Bench adapter."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .adapter import TraceTrialBenchAdapter

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate Harbor task directories for TraceTrial-Bench."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/tracetrial-bench"),
        help="Output directory for generated Harbor tasks.",
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        default=None,
        help="Comma-separated TraceTrial-Bench task IDs (defaults to all tasks in split).",
    )
    parser.add_argument(
        "--split",
        choices=("single-turn", "all"),
        default="single-turn",
        help="Task split to adapt ('single-turn' [69 tasks] or 'all' [96 tasks]).",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=None,
        help="Optional local TraceTrial-Bench checkout (skips sparse git clone).",
    )
    parser.add_argument(
        "--list-tasks",
        action="store_true",
        help="List available task IDs in the chosen split and exit.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Generate at most the first N selected tasks.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing generated task directories.",
    )

    args = parser.parse_args(argv)
    adapter = TraceTrialBenchAdapter(
        output_dir=args.output_dir,
        source_dir=args.source_dir,
        split=args.split,
    )

    if args.list_tasks:
        tasks = adapter.list_available_tasks()
        for tid in tasks:
            print(tid)
        sys.exit(0)

    selected_ids = None
    if args.task_ids and args.task_ids.lower() != "all":
        selected_ids = [t.strip() for t in args.task_ids.split(",") if t.strip()]

    written = adapter.run(
        task_ids=selected_ids,
        limit=args.limit,
        overwrite=args.overwrite,
    )
    logger.info("Generated %d TraceTrial-Bench Harbor task(s) in %s", len(written), args.output_dir)


if __name__ == "__main__":
    main()
