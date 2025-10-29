#!/usr/bin/env python3
"""
Migrate legacy flat-list instances (sre:instances) to per-instance hash docs under
SRE_INSTANCES_INDEX, ensuring the search index exists and secrets are encrypted when possible.

Usage:
    python scripts/migrate_instances_to_index_storage.py

Notes:
- Uses environment-derived settings (redis URL, password, etc.) from redis_sre_agent.core.config
- If REDIS_SRE_MASTER_KEY is not set, secrets will be left as-is and a warning printed
- On successful migration (no per-instance write errors), deletes legacy key 'sre:instances'
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add repository root to import path when run directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis_sre_agent.core.encryption import EncryptionError, encrypt_secret, is_encrypted
from redis_sre_agent.core.redis import SRE_INSTANCES_INDEX, get_instances_index, get_redis_client


def _to_epoch(ts):
    if ts is None:
        return 0.0
    try:
        if isinstance(ts, (int, float)):
            return float(ts)
        if isinstance(ts, str) and ts.endswith("Z"):
            ts = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return 0.0


async def migrate() -> tuple[int, int]:
    client = get_redis_client()
    legacy_key = "sre:instances"

    # Load legacy data
    raw = await client.get(legacy_key)
    if not raw:
        print(
            "No legacy instances found (key 'sre:instances' is empty or missing). Nothing to migrate."
        )
        return (0, 0)
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")

    try:
        instances_list = json.loads(raw)
    except Exception as e:
        print(f"❌ Failed to parse legacy instances JSON: {e}")
        raise

    if not isinstance(instances_list, list):
        print("❌ Legacy key does not contain a JSON list. Aborting.")
        return (0, 1)

    # Ensure the new index exists (best-effort)
    try:
        index = await get_instances_index()
        if not await index.exists():
            await index.create()
            print("✓ Created instances search index")
        else:
            print("✓ Instances search index already exists")
    except Exception as e:
        print(f"⚠️  Warning: could not ensure instances index exists: {e}")

    migrated = 0
    errors = 0
    now_ts = datetime.now(timezone.utc).timestamp()

    for inst in instances_list:
        try:
            inst_id = inst.get("id") or inst.get("instance_id")
            if not inst_id:
                print("⚠️  Skipping instance without an 'id'")
                continue

            # Encrypt secrets if present and not already encrypted
            for field in ("connection_url", "admin_password"):
                val = inst.get(field)
                if val:
                    try:
                        if not is_encrypted(val):
                            inst[field] = encrypt_secret(val)
                    except EncryptionError as ee:
                        print(f"⚠️  Could not encrypt {field} for {inst_id}: {ee}. Leaving as-is.")

            created_ts = _to_epoch(inst.get("created_at")) or now_ts
            updated_ts = _to_epoch(inst.get("updated_at")) or now_ts

            # Normalize index fields
            environment = (inst.get("environment") or "").lower()
            usage = (inst.get("usage") or "").lower()
            status = inst.get("status") or "unknown"
            status = status.lower() if isinstance(status, str) else "unknown"
            instance_type = inst.get("instance_type")
            if isinstance(instance_type, dict):
                instance_type = instance_type.get("value") or str(instance_type)
            if not instance_type:
                instance_type = "unknown"

            key = f"{SRE_INSTANCES_INDEX}:{inst_id}"
            await client.hset(
                key,
                mapping={
                    "name": inst.get("name") or "",
                    "environment": environment,
                    "usage": usage,
                    "instance_type": str(instance_type),
                    "user_id": inst.get("user_id") or "",
                    "status": status,
                    "created_at": created_ts,
                    "updated_at": updated_ts,
                    "data": json.dumps(inst),
                },
            )
            migrated += 1
        except Exception as e:
            print(f"❌ Error migrating instance {inst.get('id')}: {e}")
            errors += 1

    # Delete legacy key only if all docs migrated without write errors
    try:
        if errors == 0:
            await client.delete(legacy_key)
            print("✓ Deleted legacy key 'sre:instances'")
        else:
            print("⚠️  Not deleting legacy key due to migration errors")
    except Exception as e:
        print(f"⚠️  Warning: could not delete legacy key: {e}")

    print(f"\nSummary: migrated={migrated}, errors={errors}")
    return (migrated, errors)


if __name__ == "__main__":
    asyncio.run(migrate())
