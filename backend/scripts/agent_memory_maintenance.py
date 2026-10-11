"""Run from backend: python scripts/agent_memory_maintenance.py purge [--apply]."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.checkpoint import selector_loop_factory
from src.infrastructure.celery.tasks.memory_tasks import run_memory_maintenance


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Agent memory cleanup and retention; purge defaults to dry-run")
    parser.add_argument("command", choices=("cleanup", "purge"))
    parser.add_argument("--apply", action="store_true", help="Apply retention deletion instead of dry-run")
    parser.add_argument("--watch", action="store_true", help="Repeat cleanup only; never run retention purge")
    parser.add_argument("--interval", type=int, default=60, help="Cleanup watch interval in seconds (minimum 15)")
    args = parser.parse_args(argv)
    if args.watch and args.command != "cleanup":
        parser.error("--watch is only allowed for cleanup; retention purge must be invoked separately")
    if args.interval < 15:
        parser.error("--interval must be at least 15 seconds")
    return args


async def run(args):
    while True:
        result = await run_memory_maintenance(purge=args.command == "purge", dry_run=not args.apply)
        print(json.dumps(result), flush=True)
        if not args.watch:
            return
        await asyncio.sleep(args.interval)


if __name__ == "__main__":
    args = parse_args()
    with asyncio.Runner(loop_factory=selector_loop_factory) as runner:
        runner.run(run(args))
