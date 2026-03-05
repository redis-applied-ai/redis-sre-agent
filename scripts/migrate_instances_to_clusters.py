#!/usr/bin/env python3
"""Manual entrypoint for RedisInstance -> RedisCluster backfill migration."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add repository root to import path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis_sre_agent.core.migrations.instances_to_clusters import (
    run_instances_to_clusters_migration,
)


async def _main(args: argparse.Namespace) -> int:
    summary = await run_instances_to_clusters_migration(
        dry_run=args.dry_run,
        force=args.force,
        source="manual_script",
    )
    payload = summary.to_dict()
    print(json.dumps(payload, indent=2))
    return 0 if not payload.get("errors") else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill RedisCluster links for existing RedisInstance records"
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing changes")
    parser.add_argument("--force", action="store_true", help="Run even if completion marker exists")
    args = parser.parse_args()
    return asyncio.run(_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
