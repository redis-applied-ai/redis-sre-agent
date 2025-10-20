#!/usr/bin/env python3
"""
Migrate existing plaintext secrets to encrypted format.

This script:
1. Loads all instances from Redis
2. Encrypts any plaintext connection_url and admin_password fields
3. Saves them back to Redis

Usage:
    # Set master key first
    export REDIS_SRE_MASTER_KEY=$(python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())')
    # Run migration
    python scripts/migrate_encrypt_secrets.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from redis_sre_agent.core.encryption import encrypt_secret, is_encrypted
from redis_sre_agent.core.keys import RedisKeys
from redis_sre_agent.core.redis import get_redis_client


async def migrate_instances():
    """Migrate instance secrets to encrypted format."""
    try:
        redis_client = get_redis_client()
        instances_data = await redis_client.get(RedisKeys.instances_set())

        if not instances_data:
            print("No instances found in Redis.")
            return

        instances_list = json.loads(instances_data)
        print(f"\nFound {len(instances_list)} instances in Redis")
        print("=" * 80)

        migrated_count = 0
        already_encrypted_count = 0

        for inst in instances_list:
            name = inst.get("name", "unknown")
            inst_id = inst.get("id", "unknown")
            needs_migration = False

            print(f"\nProcessing: {name} (ID: {inst_id})")

            # Check connection_url
            if inst.get("connection_url"):
                if is_encrypted(inst["connection_url"]):
                    print("  ✓ connection_url already encrypted")
                    already_encrypted_count += 1
                else:
                    print("  → Encrypting connection_url...")
                    inst["connection_url"] = encrypt_secret(inst["connection_url"])
                    needs_migration = True

            # Check admin_password
            if inst.get("admin_password"):
                if is_encrypted(inst["admin_password"]):
                    print("  ✓ admin_password already encrypted")
                else:
                    print("  → Encrypting admin_password...")
                    inst["admin_password"] = encrypt_secret(inst["admin_password"])
                    needs_migration = True

            if needs_migration:
                migrated_count += 1

        # Save back to Redis
        if migrated_count > 0:
            print(f"\n{'=' * 80}")
            print(f"Saving {migrated_count} migrated instance(s) to Redis...")
            instances_data = json.dumps(instances_list)
            await redis_client.set(RedisKeys.instances_set(), instances_data)
            print("✓ Migration complete!")
        else:
            print(f"\n{'=' * 80}")
            print("No migration needed - all secrets already encrypted.")

        print("\nSummary:")
        print(f"  Total instances: {len(instances_list)}")
        print(f"  Migrated: {migrated_count}")
        print(f"  Already encrypted: {already_encrypted_count}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 80)
    print("Redis SRE Agent - Secret Encryption Migration")
    print("=" * 80)

    # Check for master key
    import os

    if not os.getenv("REDIS_SRE_MASTER_KEY"):
        print("\n❌ ERROR: REDIS_SRE_MASTER_KEY environment variable not set!")
        print("\nGenerate and set a master key:")
        print(
            "  export REDIS_SRE_MASTER_KEY=$(python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())')"
        )
        print("\n⚠️  IMPORTANT: Save this key securely! You'll need it to decrypt secrets.")
        print("   Add it to your .env file and deployment configuration.")
        sys.exit(1)

    print("\n✓ Master key configured")
    print("\nStarting migration...")

    asyncio.run(migrate_instances())
