"""
Redis SRE Agent - Interactive Demos
"""

import argparse
import asyncio
import logging
import os
import random
import time
import warnings
from typing import Optional

import httpx
import redis

from redis_sre_agent.core.instances import (
    RedisInstance,
    RedisInstanceType,
    get_instances,
    save_instances,
)
from redis_sre_agent.core.redis import get_redis_client
from redis_sre_agent.core.tasks import TaskManager, TaskStatus, create_task

DEMO_PORT = 7844
DEFAULT_REDIS_ENTERPRISE_NAME = "Redis Enterprise Demo"
DEFAULT_OSS_REDIS_NAME = "Open-Source Redis Demo"

# TODO: Suppress Pydantic protected namespace warning from dependencies
warnings.filterwarnings(
    "ignore",
    message=r"Field \"model_name\" in .* has conflict with protected namespace \"model_\"",
    category=UserWarning,
)


# ------------------------------ Demo helpers ------------------------------
# Lightweight helpers to seed demo evidence without extra deps.


def pushgateway_push(job: str, instance: str, metrics_text: str) -> bool:
    """Push Prometheus metrics to Pushgateway.

    Args:
        job: Prometheus job label
        instance: Prometheus instance label
        metrics_text: Exposition format text, e.g. "metric_name{label=\"v\"} 1\n"
    Returns:
        True on HTTP 2xx, else False
    """
    try:
        import http.client

        conn = http.client.HTTPConnection("localhost", 9091, timeout=5)
        path = f"/metrics/job/{job}/instance/{instance}"
        conn.request("PUT", path, body=metrics_text, headers={"Content-Type": "text/plain"})
        resp = conn.getresponse()
        # Drain response to allow connection reuse/cleanup
        _ = resp.read()
        conn.close()
        return 200 <= resp.status < 300
    except Exception as e:
        print(f"⚠️  Pushgateway push failed: {e}")
        return False


def loki_push(labels: dict, lines: list[str]) -> bool:
    """Push labeled log lines to Loki.

    Args:
        labels: Dict of label key/values (e.g., {"service": "redis-demo", "scenario": "1.1"})
        lines: List of log message strings. Timestamps are assigned at push time.
    Returns:
        True on HTTP 2xx, else False
    """
    try:
        import http.client
        import json

        # Loki expects ns timestamps as strings; assign current time to each line
        ts = str(int(time.time() * 1e9))
        stream = {
            "stream": labels,
            "values": [[ts, line] for line in lines],
        }
        payload = {"streams": [stream]}
        body = json.dumps(payload)

        conn = http.client.HTTPConnection("localhost", 3100, timeout=5)
        conn.request(
            "POST",
            "/loki/api/v1/push",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        _ = resp.read()
        conn.close()
        return 200 <= resp.status < 300
    except Exception as e:
        print(f"⚠️  Loki push failed: {e}")
        return False


# --------------------------------------------------------------------------


class RedisSREDemo:
    """Interactive Redis SRE Agent demonstration."""

    def __init__(self, ui_mode: bool = False):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_port: Optional[int] = None
        self.redis_url: Optional[str] = None
        self.ui_mode = ui_mode
        # Demo Tracker scenarios (CLI demos only)
        self.menu_items = [
            ("1.1", "Redis Slow Due to Host Memory Pressure", self.scenario_1_1),
            ("1.2", "Redis Network Saturation", self.scenario_1_2),
            ("2.1", "Node in Maintenance Mode (Enterprise)", self.scenario_2_1),
            ("2.2", "Cluster Rebalancing in Progress", self.scenario_2_2),
            ("3.1", "Memory Limit Reached", self.scenario_3_1),
            ("3.2", "Connection Exhaustion", self.scenario_3_2),
            ("3.3", "Slow Commands", self.scenario_3_3),
            ("3.4", "Replication Lag", self.scenario_3_4),
            ("4.1", "Master Shard Failover", self.scenario_4_1),
            ("4.2", "Shard CPU from Expensive Ops", self.scenario_4_2),
            ("4.3", "Unbalanced Shards", self.scenario_4_3),
            ("5.1", "Redis OOM Errors (Logs)", self.scenario_5_1),
            ("5.2", "Client Connection Errors (Logs)", self.scenario_5_2),
            ("6.1", "Unauthorized Access Attempts", self.scenario_6_1),
            ("6.2", "Dangerous Commands Enabled", self.scenario_6_2),
        ]
        # ID -> function map for --scenario handling
        self.scenarios = {sid: func for (sid, _label, func) in self.menu_items}
        # Static short names (exact match; case-insensitive at lookup)
        self.short_names = {
            "1.1": "host-memory-pressure",
            "1.2": "redis-network-saturation",
            "2.1": "maintenance-mode",
            "2.2": "cluster-rebalancing",
            "3.1": "memory-limit",
            "3.2": "connection-exhaustion",
            "3.3": "slow-commands",
            "3.4": "replication-lag",
            "4.1": "master-failover",
            "4.2": "shard-cpu",
            "4.3": "unbalanced-shards",
            "5.1": "oom-errors",
            "5.2": "client-connection-errors",
            "6.1": "unauthorized-access",
            "6.2": "dangerous-commands",
        }
        self.shortname_to_func = {
            v.lower(): self.scenarios[k] for k, v in self.short_names.items() if k in self.scenarios
        }

        # Finalize demo logging configuration
        self._setup_demo_logging()

    def get_scenario_func(self, selector: str):
        if not selector:
            return None
        key = selector.strip().lower()
        if key in {"all", "*"}:
            return "__ALL__"
        # Exact ID match
        if key in self.scenarios:
            return self.scenarios[key]
        # Exact short-name match
        func = self.shortname_to_func.get(key)
        if func:
            return func
        return None

    def _setup_demo_logging(self):
        """Configure logging for demo to reduce noise."""
        # Set agent and tool logging to WARNING to reduce noise during demo
        logging.getLogger("redis_sre_agent.agent").setLevel(logging.WARNING)
        logging.getLogger("redis_sre_agent.tools").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        # Keep only error/critical logs for demo experience
        demo_loggers = [
            "redis_sre_agent.agent.langgraph_agent",
            "redis_sre_agent.tools.sre_functions",
            "redis_sre_agent.tools.redis_diagnostics",
            "redis_sre_agent.tools.prometheus_client",
        ]

        for logger_name in demo_loggers:
            logging.getLogger(logger_name).setLevel(logging.ERROR)

    def print_header(self, title: str, symbol: str = "="):
        """Print a formatted header."""
        if symbol == "🧠":
            # Fix the repetitive emoji issue - use reasonable number
            print(f"\n{'=' * 15} 🧠 {title} 🧠 {'=' * 15}")
        elif symbol == "🔗":
            print(f"\n{'=' * 15} 🔗 {title} 🔗 {'=' * 15}")
        elif symbol == "⚡":
            print(f"\n{'=' * 15} ⚡ {title} ⚡ {'=' * 15}")
        elif symbol == "🏥":
            print(f"\n{'=' * 15} 🏥 {title} 🏥 {'=' * 15}")
        else:
            print(f"\n{symbol * 60}")
            print(f"🚀 {title}")
            print(f"{symbol * 60}")

    def print_step(self, step_num: int, description: str):
        """Print a formatted step."""
        print(f"\n📋 Step {step_num}: {description}")
        print("-" * 50)

    async def setup_redis_connection(self) -> bool:
        """Establish Redis connection and setup health checker."""
        # Use separate Redis instance for demo scenarios to avoid interference with agent operational data

        # Connect to separate Redis instance for demo scenarios
        self.redis_client = redis.Redis(host="localhost", port=DEMO_PORT, decode_responses=True)
        self.redis_client.ping()
        self.redis_port = DEMO_PORT
        self.redis_url = f"redis://localhost:{DEMO_PORT}/0"

        # Clear any existing data from previous demo runs to ensure clean state
        try:
            self.redis_client.flushdb()
            print(
                f"✅ Redis connection established on port {DEMO_PORT} (database cleared for clean demo)"
            )
        except redis.ConnectionError:
            print(f"❌ Redis connection failed on port {DEMO_PORT}")
            return False

        # Register the demo instance with the agent (especially important for UI mode)
        await self._register_demo_instance()

        return True

    async def _register_demo_instance(self):
        """Register or update the OSS demo Redis instance for the agent (docker hosts/ports)."""
        try:
            from urllib.parse import urlparse

            # Agent-facing URL inside docker-compose (worker/API use this)
            agent_url = "redis://redis-demo:6379/0"

            # Get existing instances
            instances = await get_instances()

            demo_instance_name = "Demo Redis (Scenarios)"
            target = None

            # Find an existing instance by name OR by URL host/port (handles older registrations)
            for inst in instances:
                try:
                    if inst.name == demo_instance_name:
                        target = inst
                        break
                    url = inst.connection_url.get_secret_value()
                    parsed = urlparse(url)
                    hostport = (
                        f"{parsed.hostname}:{parsed.port}"
                        if parsed.hostname and parsed.port
                        else ""
                    )
                    if hostport in {"redis-demo:6379", "localhost:7844", "127.0.0.1:7844"}:
                        target = inst
                        break
                except Exception:
                    continue

            if target:
                target.name = demo_instance_name
                target.connection_url = agent_url
                target.environment = getattr(target, "environment", None) or "development"
                target.usage = getattr(target, "usage", None) or "demo"
                # Ensure Loki per-instance config focuses logs on the demo container
                # Also seed Host Telemetry config so the agent can query host metrics/logs for this demo
                try:
                    ext = getattr(target, "extension_data", None) or {}

                    # Loki hints
                    loki_cfg = {"prefer_streams": [{"service": "redis-demo"}]}
                    existing_loki = ext.get("loki") if isinstance(ext.get("loki"), dict) else {}
                    ext["loki"] = {**(existing_loki or {}), **loki_cfg}

                    # Host telemetry (metrics + logs)
                    # We use Pushgateway-seeded node_exporter metrics labeled instance="demo-host"
                    # and prefer node-exporter or docker logs scoped by instance.
                    ext["host_telemetry"] = {
                        "hosts": ["demo-host"],
                        "metrics": {
                            "metric_aliases": {
                                # Memory availability percentage
                                "mem_available_pct": '100 * (node_memory_MemAvailable_bytes{instance="{host}"} / node_memory_MemTotal_bytes{instance="{host}"})',
                                # Raw memory totals
                                "mem_available_bytes": 'node_memory_MemAvailable_bytes{instance="{host}"}',
                                "mem_total_bytes": 'node_memory_MemTotal_bytes{instance="{host}"}',
                                # Swap
                                "swap_free_pct": '100 * (node_memory_SwapFree_bytes{instance="{host}"} / node_memory_SwapTotal_bytes{instance="{host}"})',
                                "swap_free_bytes": 'node_memory_SwapFree_bytes{instance="{host}"}',
                                "swap_total_bytes": 'node_memory_SwapTotal_bytes{instance="{host}"}',
                            },
                            "default_step": "30s",
                        },
                        "logs": {
                            # Prefer node-exporter logs by instance, but providers may override using per-instance loki hints
                            "stream_selector_template": '{job="node-exporter", instance="{host}"}',
                            "direction": "backward",
                            "limit": 1000,
                        },
                    }

                    target.extension_data = ext
                except Exception:
                    pass

                await save_instances(instances)
                print("✅ Updated demo instance registration (redis-demo:6379)")
            else:
                from datetime import datetime

                demo_instance = RedisInstance(
                    id=f"redis-demo-{int(datetime.now().timestamp())}",
                    name=demo_instance_name,
                    connection_url=agent_url,
                    environment="development",
                    usage="demo",
                    description=(
                        "Demo Redis instance for scenario testing. Used by demo_scenarios.py; "
                        "reachable as redis-demo:6379 from agent."
                    ),
                    notes="Registered by demo_scenarios.py. Data is cleared between runs.",
                    instance_type="oss_single",
                )
                # Seed per-instance Loki and Host Telemetry config for new demo instance
                try:
                    ext = getattr(demo_instance, "extension_data", None) or {}
                    # Loki hints
                    ext["loki"] = {
                        **(ext.get("loki", {}) or {}),
                        "prefer_streams": [{"service": "redis-demo"}],
                    }
                    # Host telemetry config
                    ext["host_telemetry"] = {
                        "hosts": ["demo-host"],
                        "metrics": {
                            "metric_aliases": {
                                "mem_available_pct": '100 * (node_memory_MemAvailable_bytes{instance="{host}"} / node_memory_MemTotal_bytes{instance="{host}"})',
                                "mem_available_bytes": 'node_memory_MemAvailable_bytes{instance="{host}"}',
                                "mem_total_bytes": 'node_memory_MemTotal_bytes{instance="{host}"}',
                                "swap_free_pct": '100 * (node_memory_SwapFree_bytes{instance="{host}"} / node_memory_SwapTotal_bytes{instance="{host}"})',
                                "swap_free_bytes": 'node_memory_SwapFree_bytes{instance="{host}"}',
                                "swap_total_bytes": 'node_memory_SwapTotal_bytes{instance="{host}"}',
                            },
                            "default_step": "30s",
                        },
                        "logs": {
                            "stream_selector_template": '{job="node-exporter", instance="{host}"}',
                            "direction": "backward",
                            "limit": 1000,
                        },
                    }
                    demo_instance.extension_data = ext
                except Exception:
                    pass
                instances.append(demo_instance)
                await save_instances(instances)
                print("✅ Registered demo instance with agent (redis-demo:6379)")

        except Exception as e:
            print(f"⚠️  Warning: Could not register demo instance: {e}")
            print("   The agent may not be able to connect to the demo instance in UI mode.")

    async def _register_enterprise_instance(
        self,
        *,
        name: str = DEFAULT_REDIS_ENTERPRISE_NAME,
        # IMPORTANT: Use docker-compose service DNS so containers can reach it
        connection_url: str = "redis://redis-enterprise-node1:12000/0",
        admin_url: str = "https://redis-enterprise-node1:9443",
        admin_username: str = "admin@redis.com",
        admin_password: str = "admin",
    ):
        """Register or update a Redis Enterprise instance for agent use.

        Ensures the agent has an instance with admin API credentials for
        cluster/node/database status tools.
        """
        try:
            instances = await get_instances()

            # Look for existing by name or matching Enterprise admin URL
            existing = None
            for inst in instances:
                try:
                    if inst.name == name:
                        existing = inst
                        break
                    itype = getattr(inst.instance_type, "value", inst.instance_type)
                    if (itype or "").lower() == "redis_enterprise" and (
                        inst.admin_url or ""
                    ) == admin_url:
                        existing = inst
                        break
                except Exception:
                    continue

            if existing:
                # Update fields to ensure correctness
                existing.connection_url = connection_url
                existing.environment = existing.environment or "production"
                existing.usage = existing.usage or "enterprise"
                existing.instance_type = RedisInstanceType.redis_enterprise
                existing.admin_url = admin_url
                existing.admin_username = admin_username
                existing.admin_password = admin_password
                # Persist
                await save_instances(instances)
                print("✅ Updated existing Redis Enterprise instance registration")
            else:
                from datetime import datetime

                new_instance = RedisInstance(
                    id=f"redis-enterprise-{int(datetime.now().timestamp())}",
                    name=name,
                    connection_url=connection_url,
                    environment="production",
                    usage="enterprise",
                    description=(
                        "Redis Enterprise demo cluster (docker-compose). Includes admin API "
                        "credentials for cluster/node tools."
                    ),
                    notes=(
                        "Automatically registered by demo_scenarios.py. Assumes cluster "
                        "created with admin@redis.com/admin on https://localhost:9443"
                    ),
                    instance_type="redis_enterprise",
                    admin_url=admin_url,
                    admin_username=admin_username,
                    admin_password=admin_password,
                )
                instances.append(new_instance)
                await save_instances(instances)
                print("✅ Registered Redis Enterprise instance with agent")
        except Exception as e:
            print(f"⚠️  Warning: Could not register Redis Enterprise instance: {e}")
            print("   The agent may not be able to use admin API tools for this scenario.")

    async def _prepare_enterprise(self):
        """Connect to local Redis Enterprise DB and register instance for agent.

        Returns:
            redis.Redis client connected to localhost:12000, or None on failure.
        """
        enterprise_url = "redis://localhost:12000/0"
        try:
            import redis as _redis

            client = _redis.from_url(enterprise_url)
            client.ping()
            print("   ✅ Connected to Redis Enterprise instance")
        except Exception as e:
            print(f"   ❌ Could not connect to Redis Enterprise: {e}")
            print("   💡 Make sure Redis Enterprise is running with the demo setup")
            print("   💡 Expected connection: redis://localhost:12000/0")
            return None

        # Ensure the agent can reach this instance via docker service hostnames
        await self._register_enterprise_instance(
            name=DEFAULT_REDIS_ENTERPRISE_NAME,
            connection_url="redis://redis-enterprise-node1:12000/0",
            admin_url="https://redis-enterprise-node1:9443",
            admin_username="admin@redis.com",
            admin_password="admin",
        )
        return client

    async def _rebalance_via_admin_api(
        self,
        db_name: str = "test-db",
        *,
        dry_run: bool = False,
        only_failovers: bool = False,
        poll_attempts: int = 10,
        poll_sleep: float = 3.0,
    ) -> dict:
        """Trigger rebalance via Redis Enterprise Admin API directly via localhost.

        Do not use RedisInstance here; this path is purely to CAUSE demo state.
        The agent should only learn via its tools at runtime.
        """
        base = "https://localhost:9443"
        auth_user = os.getenv("REDIS_ENTERPRISE_ADMIN_USER", "admin@redis.com")
        auth_pass = os.getenv("REDIS_ENTERPRISE_ADMIN_PASS", "admin")

        params = {}
        if dry_run:
            params["dry_run"] = "true"
        if only_failovers:
            params["only_failovers"] = "true"

        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            # Resolve DB UID by listing databases
            lst = await client.get(f"{base}/v1/bdbs", auth=(auth_user, auth_pass))
            lst.raise_for_status()
            try:
                dbs = (
                    lst.json()
                    if lst.headers.get("content-type", "").startswith("application/json")
                    else []
                )
            except Exception:
                dbs = []
            uid = None
            for d in dbs or []:
                try:
                    if str(d.get("name") or "").lower() == str(db_name).lower():
                        uid = int(d.get("uid"))
                        break
                except Exception:
                    continue
            if uid is None:
                raise RuntimeError(f"Database '{db_name}' not found via Admin API on localhost")

            # Trigger rebalance
            url = f"{base}/v1/bdbs/{uid}/actions/rebalance"
            resp = await client.put(url, params=params, auth=(auth_user, auth_pass))
            resp.raise_for_status()
            data = (
                resp.json()
                if resp.headers.get("content-type", "").startswith("application/json")
                else {"raw": resp.text}
            )

            # Optionally poll action status for a short period
            if not dry_run:
                action_uid = None
                try:
                    action_uid = data.get("action_uid") if isinstance(data, dict) else None
                except Exception:
                    action_uid = None
                if action_uid:
                    print(f"   Polling action status ({poll_attempts} attempts):")
                    for i in range(1, poll_attempts + 1):
                        st = await client.get(
                            f"{base}/v1/actions/{action_uid}", auth=(auth_user, auth_pass)
                        )
                        st.raise_for_status()
                        try:
                            payload = (
                                st.json()
                                if st.headers.get("content-type", "").startswith("application/json")
                                else st.text
                            )
                        except Exception:
                            payload = st.text
                        print(f"   [{i}] {payload}")
                        txt = (payload if isinstance(payload, str) else str(payload)).lower()
                        if any(k in txt for k in ("completed", "finished", "success")):
                            break
                        await asyncio.sleep(poll_sleep)
            return data

    async def _ensure_sharded_database(self, db_name: str = "test-db", min_shards: int = 3) -> None:
        """Ensure the Enterprise demo DB is multi-sharded so rebalance has work to do.

        Use localhost Admin API directly (no RedisInstance/provider) to avoid leaking
        configuration to the agent. Idempotent.
        """
        try:
            base = "https://localhost:9443"
            auth = (
                os.getenv("REDIS_ENTERPRISE_ADMIN_USER", "admin@redis.com"),
                os.getenv("REDIS_ENTERPRISE_ADMIN_PASS", "admin"),
            )

            async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
                # Find DB by name via list call
                lst = await client.get(f"{base}/v1/bdbs", auth=auth)
                lst.raise_for_status()
                try:
                    dbs = (
                        lst.json()
                        if lst.headers.get("content-type", "").startswith("application/json")
                        else []
                    )
                except Exception:
                    dbs = []
                db = None
                for d in dbs or []:
                    try:
                        if str(d.get("name") or "").lower() == str(db_name).lower():
                            db = d
                            break
                    except Exception:
                        continue
                if not db:
                    print(
                        f"   ⚠️  DB '{db_name}' not found via Admin API on localhost; skipping sharded DB check"
                    )
                    return

                uid = int(db.get("uid"))
                shards = int(db.get("shards_count") or 0)
                if shards >= int(min_shards):
                    return

                print(
                    f"   ℹ️ Ensuring '{db_name}' has at least {min_shards} shards (current: {shards})"
                )
                payload = {
                    "sharding": True,
                    "oss_sharding": True,
                    "shards_count": int(min_shards),
                    "shards_placement": "sparse",
                    "proxy_policy": "all-master-shards",
                }
                put = await client.put(f"{base}/v1/bdbs/{uid}", json=payload, auth=auth)
                put.raise_for_status()
                print("   ✅ Database reconfiguration accepted (reshard may start)")
        except Exception as e:
            print(f"   ⚠️  Could not ensure multi-shard database: {e}")

    def _docker_exec(self, args: list[str], timeout: int = 60):
        import subprocess

        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

    async def _create_shard_imbalance(
        self, db_name: str = "test-db", target_node_id: str = "1"
    ) -> None:
        """Python port of scripts/create_deliberate_shard_imbalance.sh.

        Moves all master shards for the database onto a single node. Prints details
        before/after and handles the "already imbalanced" case.
        """
        print(
            f"\n🔧 Creating deliberate shard imbalance: all master shards of '{db_name}' -> node:{target_node_id}"
        )
        # Pre-flight: container
        ps = self._docker_exec(["docker", "ps", "--format", "{{.Names}}"], timeout=20)
        if ps.returncode != 0 or "redis-enterprise-node1" not in (ps.stdout or ""):
            raise RuntimeError("redis-enterprise-node1 container not running")
        # DB exists?
        dbs = self._docker_exec(
            ["docker", "exec", "redis-enterprise-node1", "rladmin", "status", "databases"],
            timeout=30,
        )
        if dbs.returncode != 0 or (db_name not in (dbs.stdout or "")):
            raise RuntimeError(
                f"Database '{db_name}' not found. Run setup_redis_enterprise_cluster.sh first."
            )
        # Node exists?
        nodes = self._docker_exec(
            ["docker", "exec", "redis-enterprise-node1", "rladmin", "status", "nodes"], timeout=30
        )
        import re

        if nodes.returncode != 0 or not re.search(
            rf"\bnode:?\s*{re.escape(str(target_node_id))}\b", nodes.stdout or ""
        ):
            preview = "\n".join((nodes.stdout or "").splitlines()[:20])
            raise RuntimeError(
                f"Target node id '{target_node_id}' not found in cluster.\n{preview}"
            )
        # Show current shards (before)
        print("ℹ️ Current shards (before):")
        before = self._docker_exec(
            [
                "docker",
                "exec",
                "redis-enterprise-node1",
                "rladmin",
                "status",
                "shards",
                "db",
                db_name,
            ],
            timeout=30,
        )
        print("\n".join((before.stdout or "").splitlines()[:40]))
        # Migrate all master shards
        mig = self._docker_exec(
            [
                "docker",
                "exec",
                "redis-enterprise-node1",
                "rladmin",
                "migrate",
                "db",
                db_name,
                "all_master_shards",
                "target_node",
                str(target_node_id),
            ],
            timeout=180,
        )
        tail = "\n".join((mig.stdout or mig.stderr or "").splitlines()[-40:])
        if tail:
            print(tail)
        if mig.returncode != 0:
            # Verify if already imbalanced
            shards = self._docker_exec(
                [
                    "docker",
                    "exec",
                    "redis-enterprise-node1",
                    "rladmin",
                    "status",
                    "shards",
                    "db",
                    db_name,
                ],
                timeout=30,
            )
            lines = (shards.stdout or "").splitlines()
            total_masters = len([ln for ln in lines if " master " in ln])
            masters_on_target = len(
                [ln for ln in lines if (" master " in ln and f"node:{target_node_id}" in ln)]
            )
            if total_masters > 0 and masters_on_target == total_masters:
                print(f"✅ All master shards already on node:{target_node_id}; treating as success")
            else:
                raise RuntimeError(
                    f"Failed to migrate master shards to node:{target_node_id} (rc={mig.returncode})"
                )
        print("✅ Imbalance created")
        print("ℹ️ Current shards (after):")
        after = self._docker_exec(
            [
                "docker",
                "exec",
                "redis-enterprise-node1",
                "rladmin",
                "status",
                "shards",
                "db",
                db_name,
            ],
            timeout=30,
        )
        print("\n".join((after.stdout or "").splitlines()[:20]))

    def _wait_for_ui_interaction(self, scenario_name: str, scenario_description: str):
        """Wait for user to interact with the UI while scenario data is active."""
        print("\n" + "=" * 80)
        print(f"🌐 UI MODE: {scenario_name} scenario is now active!")
        print("=" * 80)
        print(f"📊 Scenario: {scenario_description}")
        print("🔗 Redis Instance (agent): redis-demo:6379")
        print(f"🔗 Redis Instance (host): localhost:{self.redis_port}")
        print("🌐 Web UI: http://localhost:3002")
        print("🔧 API: http://localhost:8000")
        print()
        print("The Redis instance has been configured with the scenario data.")
        print("You can now:")
        print("  1. Open the web UI at http://localhost:3002")
        print("  2. Select the Redis instance: 'Demo Redis (Scenarios)'")
        print("  3. Ask the agent about the current Redis state")
        print()
        print("💡 Suggested queries for this scenario:")

        # Provide scenario-specific query suggestions
        if "memory" in scenario_name.lower():
            print("  • 'Redis is using too much memory, what should I do?'")
            print("  • 'I'm getting memory pressure warnings, help me diagnose'")
            print("  • 'Check Redis memory usage and fragmentation'")
        elif "connection" in scenario_name.lower():
            print("  • 'Redis clients are getting connection errors'")
            print("  • 'I'm hitting connection limits, what's wrong?'")
            print("  • 'Check Redis connection status and limits'")
        elif "performance" in scenario_name.lower():
            print("  • 'Redis is running slowly, help me find the bottleneck'")
            print("  • 'Check for slow Redis operations'")
            print("  • 'Analyze Redis performance issues'")
        elif "enterprise" in scenario_name.lower():
            print("  • 'Redis Enterprise has low buffer settings, what are the risks?'")
            print("  • 'Analyze Redis Enterprise buffer configuration'")
            print("  • 'How should I optimize slave_buffer and client_buffer settings?'")
        else:
            print("  • 'Run a complete health check on this Redis instance'")
            print("  • 'What issues do you see with this Redis setup?'")
            print("  • 'Analyze the current Redis configuration and performance'")

        print()
        print("⏸️  Press ENTER when you're done testing in the UI to continue...")
        input()
        print("✅ Continuing with demo...")

    def show_main_menu(self) -> str:
        """Display main menu and get user selection."""
        mode_indicator = " (UI Mode)" if self.ui_mode else " (CLI Mode)"
        self.print_header(f"Redis SRE Agent - Interactive Demo{mode_indicator}")

        if self.ui_mode:
            print("\n🌐 UI MODE: Scenarios will set up data and pause for web UI interaction")
            print("   Web UI available at: http://localhost:3002")
        else:
            print("\n💻 CLI MODE: Scenarios will run agent queries directly in terminal")

        print("\nAvailable scenarios:")
        for idx, (sid, label, _func) in enumerate(self.menu_items, start=1):
            print(f"{idx}. {label} ({sid})")
        print(f"{len(self.menu_items) + 1}. 🚀 Run All Scenarios - Complete demonstration")
        print("0. 🚪 Exit")

        max_choice = str(len(self.menu_items) + 1)
        valid = ["0"] + [str(i) for i in range(1, len(self.menu_items) + 2)]
        while True:
            try:
                choice = input(f"\nSelect scenario (0-{max_choice}): ").strip()
                if choice in valid:
                    return choice
                else:
                    print(f"❌ Invalid choice, please select 0-{max_choice}")
            except KeyboardInterrupt:
                print("\n👋 Demo interrupted by user")
                return "0"

    # ---------- Demo Tracker scenario wrappers (CLI) ----------
    # Each wrapper maps an ID to an underlying implementation or a stub.
    async def scenario_1_1(self):
        """1.1 Redis Slow Due to Host Memory Pressure"""
        await self.host_memory_pressure_latency_scenario()

    async def host_memory_pressure_latency_scenario(self):
        """Simulate Redis slowdown correlated with host memory pressure (no Redis maxmemory changes).

        Seeds host memory pressure metrics/logs and generates light Redis latency signals,
        then asks the agent to correlate slow behavior with host memory pressure.
        """
        self.print_header("1.1 Redis Slow Due to Host Memory Pressure", "🐌")

        # Step 1: Seed host memory pressure evidence (Prometheus + Loki)
        self.print_step(1, "Seeding host memory pressure metrics and logs")
        try:
            # Push host memory metrics indicating pressure
            mem_total = int(8e9)  # 8 GB demo host
            mem_available = int(2e8)  # 0.2 GB available (pressure)
            swap_total = int(2e9)  # 2 GB swap
            swap_free = int(1e8)  # 0.1 GB free
            # Counters that agent examines via rate(); make them increase across scrapes
            base_pswpin = 1_000_000
            base_pswpout = 500_000
            base_pgmajfault = 10_000

            def push_pressure_sample(pswpin: int, pswpout: int, pgmaj: int) -> None:
                metrics_text = (
                    f'node_memory_MemTotal_bytes{{instance="demo-host"}} {mem_total}\n'
                    f'node_memory_MemAvailable_bytes{{instance="demo-host"}} {mem_available}\n'
                    f'node_memory_SwapTotal_bytes{{instance="demo-host"}} {swap_total}\n'
                    f'node_memory_SwapFree_bytes{{instance="demo-host"}} {swap_free}\n'
                    f'node_vmstat_pswpin{{instance="demo-host"}} {pswpin}\n'
                    f'node_vmstat_pswpout{{instance="demo-host"}} {pswpout}\n'
                    f'node_vmstat_pgmajfault{{instance="demo-host"}} {pgmaj}\n'
                    f'node_pressure_memory_some_seconds_total{{instance="demo-host"}} {pswpin / 1000.0}\n'
                    f'node_pressure_memory_full_seconds_total{{instance="demo-host"}} {pswpout / 2000.0}\n'
                )
                ok1 = pushgateway_push("demo-scenarios", "demo-host", metrics_text)
                ok2 = pushgateway_push("node", "demo-host", metrics_text)
                if ok1 or ok2:
                    print(
                        "   📊 Pushed host memory pressure metrics to Pushgateway (jobs: demo-scenarios, node)"
                    )
                else:
                    print("   ⚠️  Failed to push host metrics to Pushgateway")

            # Initial sample, then wait for Prometheus to scrape, then bump counters
            push_pressure_sample(base_pswpin, base_pswpout, base_pgmajfault)
            print("   ⏳ Waiting ~16s for Prometheus to scrape initial sample...")
            time.sleep(16)
            push_pressure_sample(base_pswpin + 250, base_pswpout + 120, base_pgmajfault + 40)
            print("   ⏳ Waiting ~16s for Prometheus to scrape second sample...")
            time.sleep(16)
            push_pressure_sample(base_pswpin + 500, base_pswpout + 240, base_pgmajfault + 80)

            # Push kernel/system log hints of pressure
            loki_push(
                {
                    "service": "redis-demo",
                    "job": "redis-demo",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "warn",
                },
                [
                    "kernel: kswapd: high memory pressure, reclaim in progress (demo)",
                    "kernel: page allocation failure: order:0, mode:0x14000c0(GFP_KERNEL) (demo)",
                    "kernel: invoked oom-killer: gfp_mask=0x14000c0, order=0, oom_score_adj=0 (demo)",
                ],
            )

            # Also push a parallel stream mimicking node-exporter to maximize matches
            loki_push(
                {
                    "service": "node-exporter",
                    "job": "node-exporter",
                    "instance": "demo-host",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "warn",
                },
                [
                    "kernel: kswapd: high memory pressure, reclaim in progress (demo)",
                    "kernel: page allocation failure: order:0, mode:0x14000c0(GFP_KERNEL) (demo)",
                    "kernel: invoked oom-killer: gfp_mask=0x14000c0, order=0, oom_score_adj=0 (demo)",
                ],
            )

            # And a docker-labeled stream to match promtail docker job patterns
            loki_push(
                {
                    "service": "kernel",
                    "job": "docker",
                    "host": "docker-desktop",
                    "instance": "demo-host",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "warn",
                },
                [
                    "kernel: kswapd: high memory pressure, reclaim in progress (demo)",
                    "kernel: page allocation failure: order:0, mode:0x14000c0(GFP_KERNEL) (demo)",
                    "kernel: invoked oom-killer: gfp_mask=0x14000c0, order=0, oom_score_adj=0 (demo)",
                ],
            )

        except Exception as e:
            print(f"   ⚠️  Evidence seeding failed: {e}")

        # Step 2: Generate light Redis latency signals (without changing Redis memory limits)
        self.print_step(2, "Generating light slowlog entries to reflect observed slowness")
        slow_times = []
        try:
            # Intentionally small CPU work to create modest slowlog entries (~50-150ms)
            slow_lua = """
            local it = tonumber(ARGV[1]) or 25000
            local r = 0
            for i=1,it do for j=1,75 do r = (r + (i*j)) % 1000 end end
            return r
            """
            for i in range(2):
                start = time.time()
                # Increase iterations to create ~50–200ms entries depending on host
                self.redis_client.eval(slow_lua, 0, str(200000 + i * 100000))
                dur = (time.time() - start) * 1000.0
                slow_times.append(dur)
                time.sleep(0.2)
        except Exception as e:
            print(f"   ⚠️  Could not generate slowlog hints: {e}")

        avg_slow_ms = sum(slow_times) / len(slow_times) if slow_times else 0.0
        print(f"   🐢 Approx observed latency from demo ops: {avg_slow_ms:.1f}ms")

        # Step 3: Ask the agent to investigate
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Redis Slow Due to Host Memory Pressure",
                f"Host MemAvailable low; swap pressure present; demo ops avg {avg_slow_ms:.1f}ms",
            )
            return

        await self._run_diagnostics_and_agent_query(
            "Redis operations seem slower than usual. Investigate whether host memory pressure is present "
            "(MemAvailable low, Swap usage high, kernel pressure logs) and correlate with Redis latency/slowlog. "
            "Provide concrete remediation steps to alleviate host-level pressure and Redis tuning if needed."
        )

        # Step 4: Reset baseline evidence
        self.print_step(3, "Resetting host memory evidence to baseline")
        try:
            base_metrics = (
                f'node_memory_MemTotal_bytes{{instance="demo-host"}} {int(8e9)}\n'
                f'node_memory_MemAvailable_bytes{{instance="demo-host"}} {int(6e9)}\n'
                f'node_memory_SwapTotal_bytes{{instance="demo-host"}} {int(2e9)}\n'
                f'node_memory_SwapFree_bytes{{instance="demo-host"}} {int(1.9e9)}\n'
            )
            pushgateway_push("demo-scenarios", "demo-host", base_metrics)
            # Redis-demo recovery line
            loki_push(
                {
                    "service": "redis-demo",
                    "job": "redis-demo",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "info",
                },
                ["system: host memory pressure alleviated (demo)"],
            )
            # Parallel recovery stream for node-exporter to match default log queries
            loki_push(
                {
                    "service": "node-exporter",
                    "job": "node-exporter",
                    "instance": "demo-host",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "info",
                },
                ["node_exporter: host memory pressure alleviated (demo)"],
            )
            # Docker-labeled recovery line to match docker job queries
            loki_push(
                {
                    "service": "kernel",
                    "job": "docker",
                    "host": "docker-desktop",
                    "instance": "demo-host",
                    "scenario": "1.1",
                    "component": "system",
                    "level": "info",
                },
                ["kernel: host memory pressure alleviated (demo)"],
            )
        except Exception:
            pass

    async def scenario_1_2(self):
        """1.2 Redis Network Saturation"""
        await self.network_saturation_scenario()

    async def scenario_2_1(self):
        """2.1 Node in Maintenance Mode (Enterprise)"""
        await self.redis_enterprise_maintenance_scenario()

    async def scenario_2_2(self):
        """2.2 Cluster Rebalancing in Progress (Enterprise)"""
        self.print_header("2.2 Cluster Rebalancing in Progress", "🔧")

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            print("   ⚠️ Proceeding with synthetic evidence only; Enterprise not reachable")

        # Best-effort: ensure no node is left in maintenance mode (from other scenarios)
        self.print_step(1, "Ensuring no Redis Enterprise node is stuck in maintenance mode")
        import subprocess

        try:
            # Attempt to turn off maintenance mode on node 2 (no-op if already off)
            off2 = subprocess.run(
                [
                    "docker",
                    "exec",
                    "redis-enterprise-node1",
                    "rladmin",
                    "node",
                    "2",
                    "maintenance_mode",
                    "off",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if off2.returncode == 0:
                print("   ✅ maintenance_mode off attempted for node 2")
        except Exception:
            # Ignore if cluster not present or single-node
            pass

        self.print_step(2, "Verifying Redis Enterprise cluster availability")
        try:
            status = subprocess.run(
                [
                    "docker",
                    "exec",
                    "redis-enterprise-node1",
                    "rladmin",
                    "status",
                    "nodes",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if status.returncode == 0:
                print("   ✅ Cluster reachable. rladmin status (truncated):")
                print("   " + "\n   ".join(status.stdout.splitlines()[:12]))
            else:
                print("   ⚠️  rladmin status failed; proceeding with synthetic evidence")
        except Exception as e:
            print(f"   ⚠️  Could not run rladmin: {e}")

        # Ensure DB is multi-sharded so rebalance has something to do
        print("\n📋 Pre-step: Ensuring 'test-db' has multiple shards for meaningful rebalance")
        await self._ensure_sharded_database(db_name="test-db", min_shards=3)

        # Create a real imbalance to give rebalance something to do
        self.print_step(3, "Creating deliberate shard imbalance (all masters on node 1)")
        try:
            await self._create_shard_imbalance(db_name="test-db", target_node_id="1")
        except Exception as e:
            print(f"   ⚠️  Python imbalance helper failed: {e}")
            print("   ⚙️  Falling back to shell script ...")
            try:
                imbalance = subprocess.run(
                    ["bash", "scripts/create_deliberate_shard_imbalance.sh", "test-db", "1"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )
                if imbalance.returncode == 0:
                    print("   ✅ Imbalance created (script). Output (truncated):")
                    print("   " + "\n   ".join((imbalance.stdout or "").splitlines()[:20]))
                else:
                    print("   ⚠️  Imbalance script returned non-zero.")
                    if imbalance.stderr:
                        print("   stderr:")
                        print("   " + "\n   ".join(imbalance.stderr.splitlines()[:10]))
            except Exception as e2:
                print(f"   ⚠️  Could not run imbalance script: {e2}")

        # Trigger an actual rebalance via REST API (prefer provider using RedisInstance)
        self.print_step(4, "Triggering rebalance via REST API")
        try:
            result = await self._rebalance_via_admin_api(db_name="test-db")
            print("   ✅ Rebalance request accepted via Admin API.")
            action_uid = None
            try:
                action_uid = result.get("action_uid") if isinstance(result, dict) else None
            except Exception:
                action_uid = None
            if action_uid:
                print(f"   action_uid={action_uid}")
        except Exception as e:
            print(f"   ⚠️  Could not trigger rebalance via Admin API: {e}")
            # Fallback to script
            try:
                rebalance = subprocess.run(
                    ["bash", "scripts/trigger_rebalance.sh", "test-db"],
                    capture_output=True,
                    text=True,
                    timeout=240,
                )
                if rebalance.returncode == 0:
                    print("   ✅ Rebalance request accepted (script fallback). Output (truncated):")
                    print("   " + "\n   ".join((rebalance.stdout or "").splitlines()[:25]))
                else:
                    print("   ⚠️  Rebalance script returned non-zero.")
                    if rebalance.stderr:
                        print("   stderr:")
                        print("   " + "\n   ".join(rebalance.stderr.splitlines()[:10]))
            except Exception as e2:
                print(f"   ⚠️  Script fallback also failed: {e2}")

        self.print_step(5, "Seeding 'rebalance in progress' evidence (metrics + logs)")
        try:
            # Metrics that dashboards/queries can surface (demo names)
            metrics_text = (
                're_rebalance_in_progress{db="demo"} 1\ndemo_rebalance_events_total{db="demo"} 1\n'
            )
            if pushgateway_push("demo-scenarios", "redis-enterprise", metrics_text):
                print("   📊 Pushed rebalance demo metrics to Pushgateway")

            # Loki log lines approximating Redis Enterprise rebalance/migration activity
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "2.2",
                    "component": "rebalance",
                    "level": "info",
                },
                [
                    "re: action rebalance started for database 'demo' (uid=1)",
                    "re: migrate_shard queued for shard 1 from node:2 to node:3 (demo)",
                    "re: action rebalance progress=30% (action_uid=demo-123)",
                ],
            )
        except Exception as e:
            print(f"   ⚠️  Evidence seeding failed: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Enterprise Cluster Rebalancing",
                "Synthetic 'rebalance in progress' state seeded; use admin-status tools to verify.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "We suspect a Redis Enterprise cluster rebalance is in progress. Please: (1) use the Redis Enterprise Admin API tools to list actions and confirm any 'rebalance' or 'migrate_shard' operations and their progress, (2) check Loki for rebalance/migration logs, (3) query Prometheus for any rebalance-related metrics, and (4) confirm no node remains in maintenance mode. Summarize findings and next steps."
            )

        # Cleanup: mark rebalance completed in evidence stream
        self.print_step(6, "Marking rebalance complete in demo evidence")
        try:
            metrics_text = (
                're_rebalance_in_progress{db="demo"} 0\ndemo_rebalance_events_total{db="demo"} 0\n'
            )
            pushgateway_push("demo-scenarios", "redis-enterprise", metrics_text)
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "2.2",
                    "component": "rebalance",
                    "level": "info",
                },
                [
                    "re: action rebalance progress=100% (action_uid=demo-123)",
                    "re: rebalance completed for database 'demo' (uid=1)",
                ],
            )
        except Exception:
            pass

    async def scenario_3_1(self):
        """3.1 Memory Limit Reached"""
        await self.memory_pressure_scenario()

    async def scenario_3_2(self):
        """3.2 Connection Exhaustion"""
        await self.connection_issues_scenario()

    async def scenario_3_3(self):
        """3.3 Slow Commands"""
        await self.performance_scenario()

    async def scenario_3_4(self):
        """3.4 Replication Lag (Synthetic evidence path)"""
        self.print_header("3.4 Replication Lag", "🔧")

        self.print_step(1, "Seeding replication lag metrics and log lines")
        try:
            # Metrics approximating lag on a replica
            metrics_text = (
                'demo_replication_lag_seconds{replica="redis-replica"} 12\n'
                'demo_replica_link_status{replica="redis-replica",status="down"} 1\n'
            )
            if pushgateway_push("demo-scenarios", "redis-demo", metrics_text):
                print("   📊 Pushed replication lag metrics to Pushgateway")

            # Loki log lines to indicate link issues
            loki_push(
                {
                    "service": "redis-demo",
                    "scenario": "3.4",
                    "component": "replication",
                    "level": "warn",
                },
                [
                    "redis-replica: master_link_status: down (demo)",
                    "redis-replica: master_last_io_seconds_ago=12 (demo)",
                ],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Failed to seed replication evidence: {e}")

        # Optional: attempt brief load to make primary stats non-zero
        self.print_step(2, "Generating small primary write burst for realism")
        try:
            pipe = self.redis_client.pipeline()
            for i in range(200):
                pipe.set(f"demo:repl:{i}", "x" * 256)
            pipe.execute()
        except Exception:
            pass

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Replication Lag",
                "Replica shows link down and lag per demo evidence; ask agent to verify via INFO replication.",
            )
            return

        await self._run_diagnostics_and_agent_query(
            "We suspect replication lag or link issues on a Redis replica for the demo instance. "
            "Use INFO replication and any available metrics/logs to confirm and propose mitigations."
        )

        # Cleanup
        self.print_step(3, "Cleanup demo replication keys and reset evidence")
        try:
            demo_keys = self.redis_client.keys("demo:repl:*")
            if demo_keys:
                self.redis_client.delete(*demo_keys)
        except Exception:
            pass
        try:
            pushgateway_push(
                "demo-scenarios",
                "redis-demo",
                'demo_replication_lag_seconds{replica="redis-replica"} 0\n',
            )
            loki_push(
                {
                    "service": "redis-demo",
                    "scenario": "3.4",
                    "component": "replication",
                    "level": "info",
                },
                ["redis-replica: link restored and lag cleared (demo)"],
            )
        except Exception:
            pass

    async def scenario_4_1(self):
        """4.1 Master Shard Failover (Enterprise)"""
        self.print_header("4.1 Master Shard Failover", "🔧")

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            print("   ⚠️ Proceeding with synthetic evidence only; Enterprise not reachable")

        self.print_step(1, "Checking cluster status (no destructive actions)")
        import subprocess

        try:
            status = subprocess.run(
                ["docker", "exec", "redis-enterprise-node1", "rladmin", "status", "shards"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if status.returncode == 0:
                print("   \u2705 rladmin status shards (truncated):")
                print("   " + "\n   ".join(status.stdout.splitlines()[:20]))
            else:
                print("   \u26a0\ufe0f  rladmin status failed; proceeding with synthetic evidence")
        except Exception as e:
            print(f"   \u26a0\ufe0f  Could not run rladmin: {e}")

        self.print_step(2, "Seeding failover evidence (metrics + logs)")
        try:
            # Demo counter and a state flag
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_failover_events_total{db="demo"} 1\n',  # event count
            )
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_failover_state{db="demo",status="in_progress"} 1\n',
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.1",
                    "component": "failover",
                    "level": "info",
                },
                [
                    "redis-enterprise: failover initiated for shard 1 (demo)",
                    "redis-enterprise: promoting replica to master (demo)",
                ],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Evidence seeding failed: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Master Shard Failover",
                "Synthetic failover event seeded; use admin-status tools to verify current shard roles.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "We suspect a Redis Enterprise failover occurred. Please investigate current shard roles, status, and impact."
            )

        # Cleanup: mark state as completed
        self.print_step(3, "Marking failover complete in demo evidence")
        try:
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_failover_state{db="demo",status="in_progress"} 0\n',
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.1",
                    "component": "failover",
                    "level": "info",
                },
                ["redis-enterprise: failover completed for shard 1 (demo)"],
            )
        except Exception:
            pass

    async def scenario_4_2(self):
        """4.2 Shard CPU from Expensive Ops (Enterprise)"""
        self.print_header("4.2 Shard CPU from Expensive Ops", "🔧")

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            print(
                "   \u26a0\ufe0f  Proceeding with synthetic evidence only; Enterprise not reachable"
            )

        self.print_step(1, "Seeding high shard CPU evidence (metrics + logs)")
        try:
            # Push demo CPU metrics emphasizing a single shard/node
            metrics_text = (
                'demo_shard_cpu_busy_percent{node="node2",shard="1"} 92\n'
                'demo_node_cpu_busy_percent{node="node2"} 88\n'
            )
            pushgateway_push("demo-scenarios", "redis-enterprise", metrics_text)
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.2",
                    "component": "cpu",
                    "level": "warn",
                },
                [
                    "redis-enterprise: high CPU observed for shard 1 on node2 (demo)",
                    "redis-enterprise: expensive operations suspected (demo)",
                ],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Failed to push CPU evidence: {e}")

        # Optional: run a very small CPU-heavy Lua once to create a hint in slowlog
        if enterprise_client is not None:
            try:
                slow_lua = """
                local it = 15000
                local r = 0
                for i=1,it do for j=1,50 do r = (r + (i*j)) % 1000 end end
                return r
                """
                enterprise_client.eval(slow_lua, 0)
                print("   \u2705 Executed minimal CPU-heavy Lua once for realism")
            except Exception:
                pass

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Shard CPU from Expensive Ops",
                "Synthetic high CPU evidence seeded; use admin node stats and Prom to verify.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "We are seeing high CPU on a Redis Enterprise shard and slowdowns. Please investigate causes and recommend mitigations."
            )

        # Cleanup baseline
        self.print_step(2, "Resetting CPU evidence to baseline")
        try:
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_shard_cpu_busy_percent{node="node2",shard="1"} 5\n',
            )
            pushgateway_push(
                "demo-scenarios", "redis-enterprise", 'demo_node_cpu_busy_percent{node="node2"} 5\n'
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.2",
                    "component": "cpu",
                    "level": "info",
                },
                ["redis-enterprise: CPU pressure alleviated (demo)"],
            )
        except Exception:
            pass

    async def scenario_4_3(self):
        """4.3 Unbalanced Shards (Enterprise)"""
        self.print_header("4.3 Unbalanced Shards", "🔧")

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            print(
                "   \u26a0\ufe0f Proceeding with synthetic evidence only; Enterprise not reachable"
            )

        self.print_step(1, "Checking shard placement (if available)")
        import subprocess

        try:
            status = subprocess.run(
                ["docker", "exec", "redis-enterprise-node1", "rladmin", "status", "shards"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if status.returncode == 0:
                print("   \u2705 rladmin status shards (truncated):")
                print("   " + "\n   ".join(status.stdout.splitlines()[:20]))
            else:
                print("   \u26a0\ufe0f  rladmin status failed; proceeding with synthetic evidence")
        except Exception as e:
            print(f"   \u26a0\ufe0f  Could not run rladmin: {e}")

        self.print_step(2, "Seeding unbalanced shard distribution evidence")
        try:
            # Push imbalance score and per-node shard counts
            metrics_text = (
                'demo_shard_imbalance_score{db="demo"} 0.78\n'
                'demo_shards_on_node{node="node2"} 10\n'
                'demo_shards_on_node{node="node3"} 2\n'
            )
            pushgateway_push("demo-scenarios", "redis-enterprise", metrics_text)
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.3",
                    "component": "placement",
                    "level": "info",
                },
                [
                    "redis-enterprise: shard distribution skew detected (demo)",
                    "redis-enterprise: consider rebalance to even shard placement (demo)",
                ],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Failed to push shard skew evidence: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Unbalanced Shards",
                "Synthetic skew metrics seeded; use admin shard listing and actions to recommend rebalance.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "Shard placement appears unbalanced across nodes. Please investigate and recommend a rebalance plan."
            )

        # Cleanup baseline
        self.print_step(3, "Resetting shard skew evidence to baseline")
        try:
            pushgateway_push(
                "demo-scenarios", "redis-enterprise", 'demo_shard_imbalance_score{db="demo"} 0.05\n'
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "4.3",
                    "component": "placement",
                    "level": "info",
                },
                ["redis-enterprise: shard distribution normalized (demo)"],
            )
        except Exception:
            pass

    async def scenario_5_1(self):
        """5.1 Redis OOM Errors (Logs-focused variant of memory pressure)"""
        self.print_header("5.1 Redis OOM Errors (Logs)", "🧠")

        self.print_step(1, "Configuring low memory limit to provoke OOM on write")
        try:
            self.redis_client.config_set("maxmemory", str(30 * 1024 * 1024))  # 30MB
            self.redis_client.config_set("maxmemory-policy", "noeviction")
        except Exception as e:
            print(f"   \u26a0\ufe0f  Could not set memory limit: {e}")

        self.print_step(2, "Loading data to ~95% of limit, then forcing an OOM")
        info = self.redis_client.info("memory")
        maxmemory = int(info.get("maxmemory", 30 * 1024 * 1024) or 30 * 1024 * 1024)
        target = int(maxmemory * 0.95)
        key_size = 4096
        loaded = 0
        pipe = self.redis_client.pipeline()
        try:
            i = 0
            while True:
                if loaded >= target:
                    break
                pipe.set(f"demo:oom:{i}", "x" * (key_size - 16))
                if i % 100 == 0:
                    pipe.execute()
                    pipe = self.redis_client.pipeline()
                    info = self.redis_client.info("memory")
                    loaded = int(info.get("used_memory", 0))
                i += 1
            pipe.execute()
        except Exception:
            # Ignore mid-load errors; proceed to OOM attempt
            pass

        # Attempt a write expected to fail with OOM
        self.print_step(3, "Triggering an OOM and capturing the error for logs")
        oom_msg = None
        try:
            self.redis_client.set("demo:oom:final", "y" * (key_size * 8))
        except Exception as e:
            oom_msg = str(e)
            print(f"   🚨 OOM encountered as expected: {oom_msg}")

        # Push Loki log lines emphasizing OOM
        self.print_step(4, "Pushing OOM error lines to Loki and metric to Pushgateway")
        try:
            if oom_msg is None:
                oom_msg = "OOM command not allowed when used memory > 'maxmemory' (demo)"
            loki_push(
                {
                    "service": "redis-demo",
                    "scenario": "5.1",
                    "component": "memory",
                    "level": "error",
                },
                [
                    f"redis: {oom_msg}",
                    "redis: client experienced memory limit violation (demo)",
                ],
            )
            pushgateway_push(
                "demo-scenarios", "redis-demo", 'demo_oom_events_total{instance="redis-demo"} 1\n'
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Failed to push OOM evidence: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Redis OOM Errors",
                "Redis configured with low maxmemory; OOM log lines available in Loki (demo)",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "Users report write failures due to OOM conditions. Analyze memory settings and logs to "
                "confirm the OOM and propose remediation (policy, key TTLs, memory optimization)."
            )

        # Cleanup
        self.print_step(5, "Cleaning demo keys and restoring memory settings")
        try:
            keys = self.redis_client.keys("demo:oom:*")
            if keys:
                self.redis_client.delete(*keys)
            self.redis_client.config_set("maxmemory", "0")
            self.redis_client.config_set("maxmemory-policy", "noeviction")
            # Baseline evidence
            pushgateway_push(
                "demo-scenarios", "redis-demo", 'demo_oom_events_total{instance="redis-demo"} 0\n'
            )
            loki_push(
                {
                    "service": "redis-demo",
                    "scenario": "5.1",
                    "component": "memory",
                    "level": "info",
                },
                ["redis: OOM condition cleared and memory settings restored (demo)"],
            )
        except Exception:
            pass

    async def scenario_5_2(self):
        """5.2 Client Connection Errors (Logs)"""
        # Reuse connection issues (already seeds logs) for now
        await self.connection_issues_scenario()

    async def scenario_6_1(self):
        """6.1 Unauthorized Access Attempts (ACL + logs)"""
        self.print_header("6.1 Unauthorized Access Attempts", "🔧")

        self.print_step(1, "Creating a limited ACL user and provoking denied commands")
        limited_user = "demo_limited"
        limited_pass = "limitedpass"
        created_user = False
        try:
            # Reset/create a limited user that can only GET, no SET
            self.redis_client.execute_command(
                "ACL", "SETUSER", limited_user, "on", "reset", f">{limited_pass}", "~*", "+get"
            )
            created_user = True
            print("   ✅ Created ACL user 'demo_limited' with +get only")
        except Exception as e:
            print(f"   ⚠️  Could not create limited user: {e}")

        # Attempt unauthorized operations with the limited user
        denied_msgs = []
        if created_user:
            try:
                client = redis.Redis(
                    host="localhost",
                    port=self.redis_port,
                    username=limited_user,
                    password=limited_pass,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                client.ping()
                try:
                    client.set("demo:acl:test", "x")
                except Exception as e:
                    msg = str(e)
                    denied_msgs.append(msg)
                    print(f"   🚫 Unauthorized SET denied as expected: {msg}")
                try:
                    client.config_get("maxmemory")
                except Exception as e:
                    msg = str(e)
                    denied_msgs.append(msg)
                    print(f"   🚫 Unauthorized CONFIG denied as expected: {msg}")
            except Exception as e:
                print(f"   ⚠️  Could not connect as limited user: {e}")

        self.print_step(2, "Reading ACL LOG (best-effort) and pushing Loki/metrics evidence")
        acl_entries = []
        try:
            # Read a few ACL log entries to see the violations
            acl_entries = self.redis_client.execute_command("ACL", "LOG", 5)
            # Normalize entries to strings for display/push
            acl_lines = []
            if isinstance(acl_entries, list):
                for entry in acl_entries:
                    try:
                        user = entry.get("user", "?") if hasattr(entry, "get") else "?"
                        reason = entry.get("reason", "?") if hasattr(entry, "get") else "?"
                        cmd = entry.get("cmd", "?") if hasattr(entry, "get") else "?"
                        acl_lines.append(f"ACL LOG: user={user} reason={reason} cmd={cmd}")
                    except Exception:
                        pass
            # Push Loki lines summarizing unauthorized attempts
            lines = [
                "redis: unauthorized command attempt detected (demo)",
            ]
            lines.extend([f"redis: {m}" for m in denied_msgs[:2]])
            lines.extend(acl_lines[:2])
            loki_push(
                {"service": "redis-demo", "scenario": "6.1", "component": "auth", "level": "warn"},
                lines or ["redis: unauthorized access attempts observed (demo)"],
            )
            # Metric for count of unauthorized attempts (demo)
            pushgateway_push(
                "demo-scenarios",
                "redis-demo",
                f'demo_unauthorized_attempts_total{{instance="redis-demo"}} {max(1, len(denied_msgs))}\n',
            )
        except Exception as e:
            print(f"   ⚠️  Could not read ACL LOG or push evidence: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Unauthorized Access Attempts",
                "ACL user with restricted permissions triggered denied commands; Loki lines and a metric were pushed.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "Investigate recent unauthorized Redis access attempts. Review ACL LOG and recommend access controls, "
                "password policies, and monitoring alerts."
            )

        # Cleanup
        self.print_step(3, "Cleaning up ACL user and resetting evidence")
        try:
            if created_user:
                self.redis_client.execute_command("ACL", "DELUSER", limited_user)
                print("   🧹 Removed ACL user 'demo_limited'")
            pushgateway_push(
                "demo-scenarios",
                "redis-demo",
                'demo_unauthorized_attempts_total{instance="redis-demo"} 0\n',
            )
            loki_push(
                {"service": "redis-demo", "scenario": "6.1", "component": "auth", "level": "info"},
                ["redis: unauthorized access alerts cleared (demo)"],
            )
        except Exception:
            pass

    async def scenario_6_2(self):
        """6.2 Dangerous Commands Enabled (Enterprise)"""
        self.print_header("6.2 Dangerous Commands Enabled", "🛠️")

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            print(
                "   \u26a0\ufe0f Proceeding with synthetic evidence only; Enterprise not reachable"
            )

        self.print_step(1, "Seeding evidence that disabled_commands may be unsafe/empty")
        try:
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_dangerous_commands_enabled{db="demo"} 1\n',
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "6.2",
                    "component": "config",
                    "level": "warn",
                },
                [
                    "redis-enterprise: database 'demo' disabled_commands is empty (demo)",
                    "redis-enterprise: destructive commands may be enabled (demo)",
                ],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Failed to push dangerous-commands evidence: {e}")

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Dangerous Commands Enabled",
                "Synthetic config risk seeded; ask agent to check admin API for disabled_commands and recommend safe defaults.",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                "We suspect unsafe commands may be enabled on a Redis Enterprise database. Please investigate configuration and recommend hardening."
            )

        # Cleanup baseline
        self.print_step(2, "Resetting dangerous-commands evidence to baseline")
        try:
            pushgateway_push(
                "demo-scenarios",
                "redis-enterprise",
                'demo_dangerous_commands_enabled{db="demo"} 0\n',
            )
            loki_push(
                {
                    "service": "redis-enterprise",
                    "job": "redis-enterprise",
                    "scenario": "6.2",
                    "component": "config",
                    "level": "info",
                },
                ["redis-enterprise: recommended disabled_commands applied (demo)"],
            )
        except Exception:
            pass

    # ---------------------------------------------------------

    async def memory_pressure_scenario(self):
        """Run memory pressure analysis scenario."""

        self.print_header("Memory Pressure Analysis Scenario", "🧠")

        # Get baseline memory info
        initial_info = self.redis_client.info("memory")
        initial_memory = initial_info.get("used_memory", 0)
        maxmemory = initial_info.get("maxmemory", 0)

        self.print_step(1, "Setting up memory pressure scenario")

        # Set a memory limit to create realistic pressure scenario
        # Target: Create 80-90% memory utilization for demonstration
        target_memory_mb = 50  # 50MB limit for demo
        target_memory_bytes = target_memory_mb * 1024 * 1024

        print(f"   Initial memory usage: {initial_memory / (1024 * 1024):.2f} MB")
        print(f"   Setting maxmemory to {target_memory_mb} MB to create pressure scenario...")

        # Configure Redis for memory pressure scenario
        # Create a dangerous scenario: high memory usage with no eviction policy
        self.redis_client.config_set("maxmemory", str(target_memory_bytes))
        self.redis_client.config_set(
            "maxmemory-policy", "noeviction"
        )  # No eviction = potential OOM!

        # Verify the configuration was set
        updated_info = self.redis_client.info("memory")
        maxmemory = updated_info.get("maxmemory", 0)
        print(f"   Memory limit set to: {maxmemory / (1024 * 1024):.2f} MB")
        print(f"   Current utilization: {(initial_memory / maxmemory * 100):.1f}%")

        self.print_step(2, "Loading data to approach memory limit")

        # Clear any existing demo keys first
        existing_keys = []
        for pattern in ["user:profile:*", "product:details:*", "order:data:*"]:
            existing_keys.extend(self.redis_client.keys(pattern))
        if existing_keys:
            self.redis_client.delete(*existing_keys)
            print(f"   Cleared {len(existing_keys)} existing demo keys")

        # Get current memory usage after clearing keys
        current_info = self.redis_client.info("memory")
        current_memory = current_info.get("used_memory", 0)

        # Calculate data size to create memory pressure (target ~85% utilization)
        target_utilization = 0.85  # 85% utilization
        target_total_memory = int(maxmemory * target_utilization)
        target_data_size = target_total_memory - current_memory

        key_size = 8192  # 8KB per key
        estimated_keys = max(100, target_data_size // key_size)  # At least 100 keys

        print(f"   Target data size: {target_data_size / (1024 * 1024):.2f} MB")
        print(f"   Loading approximately {estimated_keys} keys to create memory pressure...")

        # Load data in batches and monitor memory usage
        batch_size = 50
        keys_loaded = 0

        for batch_start in range(0, estimated_keys, batch_size):
            batch_end = min(batch_start + batch_size, estimated_keys)
            pipe = self.redis_client.pipeline()

            for i in range(batch_start, batch_end):
                # Create realistic key patterns that look like persistent application data
                if i % 3 == 0:
                    key = f"user:profile:{i:04d}"
                elif i % 3 == 1:
                    key = f"product:details:{i:04d}"
                else:
                    key = f"order:data:{i:04d}"
                value = f"data:{i}:{'x' * (key_size - 20)}"
                pipe.set(key, value)  # No TTL = permanent data

            try:
                pipe.execute()
                keys_loaded = batch_end

                # Check memory usage after each batch
                current_info = self.redis_client.info("memory")
                current_memory = current_info.get("used_memory", 0)
                current_utilization = current_memory / maxmemory * 100

                print(
                    f"   Progress: {keys_loaded}/{estimated_keys} keys, Memory: {current_memory / (1024 * 1024):.1f}MB ({current_utilization:.1f}%)"
                )

                # Stop if we're approaching the limit to avoid evictions during loading
                if current_utilization > 80:
                    print(
                        f"   ⚠️  Approaching memory limit ({current_utilization:.1f}%), stopping data load"
                    )
                    break

            except Exception as e:
                print(f"   ⚠️  Memory pressure detected during loading: {str(e)}")
                break

            time.sleep(0.1)  # Brief pause between batches

        time.sleep(2)  # Wait for Redis to update memory stats

        self.print_step(3, "Analyzing memory pressure situation")
        final_info = self.redis_client.info("memory")
        final_memory = final_info.get("used_memory", 0)
        maxmemory = final_info.get("maxmemory", 0)  # Re-fetch in case it changed

        utilization = (final_memory / maxmemory * 100) if maxmemory > 0 else 0

        print(f"   Final memory usage: {final_memory / (1024 * 1024):.2f} MB")
        print(f"   Memory limit: {maxmemory / (1024 * 1024):.2f} MB")
        print(f"   Memory utilization: {utilization:.1f}%")
        print(f"   Keys successfully loaded: {keys_loaded}")

        # Check for evictions
        evicted_keys = final_info.get("evicted_keys", 0)
        if evicted_keys > 0:
            print(f"   🚨 EVICTIONS DETECTED: {evicted_keys} keys evicted")

        # Step 4: Seed demo metrics (Prometheus/Pushgateway) and logs (Loki)
        self.print_step(4, "Seeding demo metrics (Pushgateway) and logs (Loki)")
        try:
            mem_total = int(8e9)  # 8 GB demo host
            mem_available = int(max(0, 2e8))  # 0.2 GB available (pressure)
            metrics_text = (
                f'node_memory_MemTotal_bytes{{instance="demo-host"}} {mem_total}\n'
                f'node_memory_MemAvailable_bytes{{instance="demo-host"}} {mem_available}\n'
            )
            if pushgateway_push("demo-scenarios", "demo-host", metrics_text):
                print(
                    "   📊 Pushed host memory pressure metrics to Pushgateway (job=demo-scenarios)"
                )
            else:
                print("   ⚠️  Failed to push memory metrics to Pushgateway")

            loki_labels = {
                "service": "redis-demo",
                "scenario": "3.1",
                "component": "system",
                "level": "warn",
            }
            loki_lines = [
                "redis: nearing configured maxmemory; evictions or OOM possible (demo)",
                "redis: memory fragmentation rising; consider tuning allocator (demo)",
            ]
            if loki_push(loki_labels, loki_lines):
                print("   📝 Pushed memory pressure log lines to Loki")
            else:
                print("   ⚠️  Failed to push memory pressure logs to Loki")
        except Exception as e:
            print(f"   ⚠️  Seeding demo evidence failed: {e}")

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Memory Pressure Analysis",
                f"Redis loaded with {keys_loaded:,} keys using {utilization:.1f}% of {maxmemory / (1024 * 1024):.1f} MB limit",
            )
            # Note: Baseline metrics will be pushed during cleanup.
            return

        # Consult the agent - let it gather its own diagnostics
        await self._run_diagnostics_and_agent_query(
            "The application team has reported performance issues with this Redis instance."
            "Please analyze the situation and provide immediate remediation steps."
        )

        # Cleanup and restore settings
        self.print_step(5, "Cleaning up and restoring settings")
        demo_keys = []
        for pattern in ["user:profile:*", "product:details:*", "order:data:*"]:
            demo_keys.extend(self.redis_client.keys(pattern))
        if demo_keys:
            self.redis_client.delete(*demo_keys)
            print(f"   Cleaned up {len(demo_keys)} demo keys")

        # Restore original maxmemory setting (0 = unlimited)
        self.redis_client.config_set("maxmemory", "0")
        self.redis_client.config_set("maxmemory-policy", "noeviction")
        print("   Restored original Redis memory settings")

        restored_info = self.redis_client.info("memory")
        restored_memory = restored_info.get("used_memory", 0)
        print(f"   Final memory usage: {restored_memory / (1024 * 1024):.2f} MB (unlimited)")

        # Push baseline host memory metrics and a recovery log entry
        try:
            metrics_text = (
                f'node_memory_MemTotal_bytes{{instance="demo-host"}} {int(8e9)}\n'  # keep total constant
                f'node_memory_MemAvailable_bytes{{instance="demo-host"}} {int(6e9)}\n'  # recover to 6 GB free
            )
            if pushgateway_push("demo-scenarios", "demo-host", metrics_text):
                print("   📊 Pushed baseline host memory metrics to Pushgateway")
            loki_push(
                {
                    "service": "redis-demo",
                    "scenario": "3.1",
                    "component": "system",
                    "level": "info",
                },
                ["redis: memory utilization back to baseline; pressure resolved (demo)"],
            )
        except Exception as e:
            print(f"   \u26a0\ufe0f  Baseline metric/log push failed: {e}")

    async def connection_issues_scenario(self):
        """Simulate connection issues and demonstrate troubleshooting."""
        self.print_header("Connection Issues Analysis Scenario", "🔗")

        self.print_step(1, "Establishing clean baseline connection state")

        # Ensure we're starting with a clean slate
        self.redis_client.flushdb()

        # Get baseline connection info (should be just our demo connection)
        baseline_info = self.redis_client.info("clients")
        baseline_clients = baseline_info.get("connected_clients", 0)

        # Get original maxclients setting
        try:
            maxclients_result = self.redis_client.config_get("maxclients")
            original_maxclients = int(maxclients_result.get("maxclients", 10000))
        except Exception:
            original_maxclients = 10000

        print(f"   Baseline connected clients: {baseline_clients} (should be 1-2 for clean demo)")
        print(f"   Original maximum clients: {original_maxclients}")

        # Verify we have a clean environment
        if baseline_clients > 3:
            print(f"   ⚠️  Warning: {baseline_clients} existing connections detected")
            print("   This may indicate a shared Redis instance - results may be affected")

        self.print_step(2, "Creating connection pressure scenario")

        # Set a low connection limit to create a realistic demo scenario
        # This simulates a constrained environment or misconfiguration
        demo_maxclients = 25  # Very low limit to ensure we can hit it with demo connections

        print(f"   Setting maxclients to {demo_maxclients} for connection pressure demo...")
        self.redis_client.config_set("maxclients", str(demo_maxclients))
        # Verify the setting was applied
        updated_result = self.redis_client.config_get("maxclients")
        current_maxclients = int(updated_result.get("maxclients", demo_maxclients))
        print(f"   Connection limit reduced to: {current_maxclients}")
        print(f"   Current utilization: {(baseline_clients / current_maxclients * 100):.1f}%")

        self.print_step(3, "Simulating connection pressure and creating blocked clients")

        # Create connections that will approach the limit
        test_connections = []
        # Target 90% of the connection limit, accounting for baseline
        target_total_clients = int(current_maxclients * 0.9)
        target_new_connections = target_total_clients - baseline_clients
        target_new_connections = max(
            15, min(target_new_connections, current_maxclients - baseline_clients - 2)
        )

        print(f"   Attempting to create {target_new_connections} concurrent connections...")
        print(
            f"   Target total clients: {target_total_clients} (~90% of {current_maxclients} limit)"
        )
        print("   This should create clear connection pressure metrics...")

        connection_errors = 0
        successful_connections = 0

        try:
            for i in range(target_new_connections):
                try:
                    conn = redis.Redis(
                        host="localhost",
                        port=self.redis_port,
                        decode_responses=True,
                        socket_connect_timeout=2,  # Short timeout to detect connection issues
                        socket_timeout=2,
                    )
                    conn.ping()  # Ensure connection is established
                    test_connections.append(conn)
                    successful_connections += 1

                    if (i + 1) % 15 == 0 or i == target_new_connections - 1:
                        print(
                            f"   Progress: {i + 1}/{target_new_connections} connections attempted..."
                        )

                    # Add some delay to simulate realistic connection patterns
                    time.sleep(0.05)

                except redis.ConnectionError as e:
                    connection_errors += 1
                    if connection_errors == 1:
                        print(f"   ⚠️  Connection rejected: {str(e)}")
                        print("   This indicates we're hitting Redis connection limits!")
                    break  # Stop trying once we hit the limit
                except Exception as e:
                    connection_errors += 1
                    if connection_errors <= 3:  # Don't spam errors
                        print(f"   ❌ Connection error: {str(e)}")

            # Check connection state after simulation
            time.sleep(1)
            clients_info_after = self.redis_client.info("clients")
            clients_after = clients_info_after.get("connected_clients", 0)

            print(f"   ✅ Successfully created: {successful_connections} connections")
            print(f"   ❌ Connection errors: {connection_errors}")
            print(f"   📊 Total connected clients: {clients_after}")
            print(
                f"   📈 Connection utilization: {(clients_after / current_maxclients * 100):.1f}%"
            )

            # Create blocked client scenario using BLPOP operations
            print("   🧪 Creating blocked clients to demonstrate client queue issues...")
            blocked_clients_created = 0

            # Use some of the existing connections to create blocking operations
            for i in range(min(10, len(test_connections))):
                try:
                    conn = test_connections[i]
                    # Start BLPOP operations on non-existent keys (will block indefinitely)
                    # Use asyncio to run these in background without blocking the demo
                    import threading

                    def blocking_operation(connection, key_name):
                        try:
                            # This will block until timeout or key appears
                            connection.blpop([key_name], timeout=30)
                        except Exception:
                            pass  # Expected timeout or connection error

                    thread = threading.Thread(
                        target=blocking_operation, args=(conn, f"nonexistent_blocking_key_{i}")
                    )
                    thread.daemon = True
                    thread.start()
                    blocked_clients_created += 1
                    time.sleep(0.1)  # Brief delay between blocking operations
                except Exception as e:
                    print(f"   Warning: Could not create blocking operation: {e}")
                    break

            # Wait for blocked clients to register
            time.sleep(2)

            # Check for blocked clients in metrics
            final_clients_info = self.redis_client.info("clients")
            blocked_clients = final_clients_info.get("blocked_clients", 0)
            total_clients = final_clients_info.get("connected_clients", 0)

            print(f"   📋 Blocked clients created: {blocked_clients_created}")
            print(f"   📊 Redis reports blocked clients: {blocked_clients}")
            print(f"   📊 Total connected clients: {total_clients}")

            if blocked_clients > 0:
                print("   🚨 BLOCKED CLIENTS DETECTED - This indicates client queue issues!")

            utilization = (
                (total_clients / current_maxclients * 100) if current_maxclients > 0 else 0
            )

            if utilization > 90:
                print("   🚨 CRITICAL: Connection exhaustion imminent!")
            elif utilization > 80:
                print("   🚨 HIGH CONNECTION USAGE DETECTED!")
            elif utilization > 60:
                print("   ⚠️  ELEVATED CONNECTION USAGE")

            # Force additional connection attempts to generate rejection metrics
            print("   🧪 Testing connection rejection behavior...")
            extra_attempts = 8
            rejected_attempts = 0
            rejection_errors = []

            for i in range(extra_attempts):
                try:
                    extra_conn = redis.Redis(
                        host="localhost",
                        port=self.redis_port,
                        socket_connect_timeout=1,
                        socket_timeout=1,
                    )
                    extra_conn.ping()
                    test_connections.append(extra_conn)
                except redis.ConnectionError as e:
                    rejected_attempts += 1
                    rejection_errors.append(str(e))
                except Exception as e:
                    rejected_attempts += 1
                    rejection_errors.append(f"Connection error: {str(e)}")

            if rejected_attempts > 0:
                print(f"   🚨 {rejected_attempts}/{extra_attempts} connection attempts rejected!")
                print("   📊 This creates visible connection_rejected_* metrics in Redis")

            # Seed logs/metrics for connection exhaustion evidence
            try:
                metrics_text = (
                    f'demo_redis_blocked_clients{{instance="redis-demo"}} {blocked_clients}\n'
                    f'demo_redis_connection_rejections_total{{instance="redis-demo"}} {rejected_attempts}\n'
                )
                pushgateway_push("demo-scenarios", "redis-demo", metrics_text)
                loki_push(
                    {
                        "service": "redis-demo",
                        "scenario": "3.2",
                        "component": "clients",
                        "level": "error",
                    },
                    [
                        "redis: max number of clients reached (demo)",
                        f"redis: blocked_clients={blocked_clients} connection_rejections={rejected_attempts} (demo)",
                    ],
                )
            except Exception as e:
                print(f"   \u26a0\ufe0f  Failed to push connection exhaustion evidence: {e}")

            # Handle UI mode vs CLI mode
            if self.ui_mode:
                self._wait_for_ui_interaction(
                    "Connection Issues Analysis",
                    f"Redis with {total_clients} connected clients (max: {current_maxclients}), {blocked_clients} blocked clients, {rejected_attempts} recent rejections",
                )
            else:
                # Run agent consultation with connection-focused query
                await self._run_diagnostics_and_agent_query(
                    "We are seeing connection timeouts and some blocked clients. Please investigate connection issues and recommend immediate steps."
                )

        finally:
            # Cleanup test connections
            self.print_step(4, "Cleaning up test connections and restoring settings")
            for conn in test_connections:
                try:
                    conn.close()
                except Exception:
                    pass

            # Restore original maxclients setting
            self.redis_client.config_set("maxclients", str(original_maxclients))
            print(f"   Restored maxclients to original value: {original_maxclients}")

            time.sleep(1)
            final_clients_info = self.redis_client.info("clients")
            final_clients = final_clients_info.get("connected_clients", 0)
            print(f"   Final connection count: {final_clients}")

    async def network_saturation_scenario(self):
        """Simulate host/network saturation and demonstrate analysis.

        This uses Pushgateway to publish high network throughput/drop metrics and
        Loki to publish saturation log lines. Optionally generates brief Redis
        traffic for realism.
        """
        self.print_header("Redis Network Saturation Scenario", "🔗")

        self.print_step(1, "Seeding high network throughput/drop metrics via Pushgateway")
        try:
            metrics_text = (
                # Custom demo metrics to avoid collision with real node_exporter
                'demo_network_tx_bytes_per_sec{instance="redis-demo",device="eth0"} 9.5e8\n'
                'demo_network_rx_bytes_per_sec{instance="redis-demo",device="eth0"} 9.2e8\n'
                'demo_network_drop_rate_per_sec{instance="redis-demo",device="eth0"} 500\n'
            )
            if pushgateway_push("demo-scenarios", "redis-demo", metrics_text):
                print(
                    "   📊 Pushed demo network saturation metrics to Pushgateway (job=demo-scenarios)"
                )
            else:
                print("   ⚠️  Failed to push network metrics to Pushgateway")
        except Exception as e:
            print(f"   ⚠️  Pushgateway error: {e}")

        self.print_step(2, "Publishing saturation log lines to Loki")
        try:
            loki_labels = {
                "service": "redis-demo",
                "scenario": "1.2",
                "component": "net",
                "level": "warn",
            }
            lines = [
                "kernel: eth0: TX queue length 1000 exceeded, possible congestion (demo)",
                "app: upstream redis latency increasing due to network saturation (demo)",
            ]
            if loki_push(loki_labels, lines):
                print("   📝 Pushed network saturation log lines to Loki")
        except Exception as e:
            print(f"   ⚠️  Loki push failed: {e}")

        self.print_step(3, "Generating brief Redis traffic for realism")
        try:
            pipe = self.redis_client.pipeline()
            for i in range(200):
                pipe.set(f"demo:net:{i}", "x" * 128)
            pipe.execute()
            for i in range(200):
                _ = self.redis_client.get(f"demo:net:{i}")
        except Exception:
            pass

        # UI vs CLI handling
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Redis Network Saturation",
                "Host-level network throughput approaching link capacity with packet drops (demo)",
            )
            return

        await self._run_diagnostics_and_agent_query(
            "Reports indicate Redis connectivity issues. Analyze likely causes and mitigations. "
            "Check your logs and metrics tools, and anything else you can."
        )

        # Cleanup
        self.print_step(4, "Cleanup demo network keys and reset state")
        try:
            demo_keys = self.redis_client.keys("demo:net:*")
            if demo_keys:
                self.redis_client.delete(*demo_keys)
        except Exception:
            pass

    async def performance_scenario(self):
        """Simulate performance issues and demonstrate analysis."""
        self.print_header("Performance Analysis Scenario", "⚡")

        self.print_step(1, "Setting up performance test data")

        # Create different data structures to test performance
        test_data = {
            "simple_keys": 1000,
            "hash_keys": 100,
            "list_keys": 50,
            "set_keys": 50,
            "sorted_set_keys": 50,
        }

        print("   Creating test data structures...")

        # Clean up any existing test data
        existing_keys = self.redis_client.keys("demo:perf:*")
        if existing_keys:
            self.redis_client.delete(*existing_keys)

        # Create simple string keys
        pipe = self.redis_client.pipeline()
        for i in range(test_data["simple_keys"]):
            pipe.set(f"demo:perf:string:{i}", f"value_{i}_{random.randint(1000, 9999)}")
        pipe.execute()
        print(f"   ✅ Created {test_data['simple_keys']} string keys")

        # Create hash keys
        for i in range(test_data["hash_keys"]):
            hash_data = {f"field_{j}": f"value_{j}_{random.randint(1000, 9999)}" for j in range(20)}
            self.redis_client.hset(f"demo:perf:hash:{i}", mapping=hash_data)
        print(f"   ✅ Created {test_data['hash_keys']} hash keys")

        # Create list keys
        for i in range(test_data["list_keys"]):
            key = f"demo:perf:list:{i}"
            for j in range(100):
                self.redis_client.lpush(key, f"item_{j}_{random.randint(1000, 9999)}")
        print(f"   ✅ Created {test_data['list_keys']} list keys")

        self.print_step(2, "Running performance analysis and creating slow operations")

        # Create intentionally slow Lua script to generate real slowlog entries
        slow_lua_script = """
        -- Intentionally slow Lua script for performance demo
        local start_time = redis.call('TIME')
        local iterations = tonumber(ARGV[1]) or 100000

        -- Simulate CPU-intensive work
        local result = 0
        for i = 1, iterations do
            for j = 1, 100 do
                result = result + (i * j) % 1000
            end
        end

        -- Also do some Redis operations to make it realistic
        for i = 1, 10 do
            redis.call('SET', 'temp:slow:' .. i, 'processing_' .. result .. '_' .. i)
            redis.call('GET', 'temp:slow:' .. i)
            redis.call('DEL', 'temp:slow:' .. i)
        end

        local end_time = redis.call('TIME')
        return {result, end_time[1] - start_time[1], end_time[2] - start_time[2]}
        """

        print("   Creating intentionally slow operations to populate slowlog...")

        # Execute slow Lua script multiple times to create slowlog entries
        slow_times = []
        for i in range(3):
            try:
                print(f"   Executing slow operation {i + 1}/3...")
                start_time = time.time()
                # Adjust iterations to create operations that take 100-500ms
                self.redis_client.eval(slow_lua_script, 0, str(50000 + i * 10000))
                duration = time.time() - start_time
                slow_times.append(duration * 1000)  # Convert to milliseconds
                print(f"   Slow operation {i + 1} completed in {duration * 1000:.1f}ms")
                time.sleep(0.5)  # Brief pause between slow operations
            except Exception as e:
                print(f"   Warning: Slow operation {i + 1} failed: {e}")

        # Add some additional slow KEYS operations for variety in slowlog
        print("   Adding slow KEYS operations...")
        keys_times = []
        for pattern in ["demo:perf:*", "*perf*", "demo:*"]:
            start_time = time.time()
            keys = self.redis_client.keys(pattern)
            duration = time.time() - start_time
            keys_times.append(duration * 1000)
            print(f"   KEYS {pattern} found {len(keys)} keys in {duration * 1000:.1f}ms")

        # Test normal operations for comparison
        print("   Testing normal operation performance for comparison...")

        # Test string operations
        start_time = time.time()
        for i in range(100):
            self.redis_client.get(f"demo:perf:string:{i}")
        string_time = time.time() - start_time
        print(
            f"   100 GET operations: {string_time:.3f} seconds ({string_time / 100 * 1000:.2f}ms avg)"
        )

        # Test hash operations
        start_time = time.time()
        for i in range(50):
            self.redis_client.hgetall(f"demo:perf:hash:{i}")
        hash_time = time.time() - start_time
        print(
            f"   50 HGETALL operations: {hash_time:.3f} seconds ({hash_time / 50 * 1000:.2f}ms avg)"
        )

        # Show performance comparison
        avg_slow_time = sum(slow_times) / len(slow_times) if slow_times else 0
        avg_keys_time = sum(keys_times) / len(keys_times) if keys_times else 0

        print("\n   📊 Performance Summary:")
        print(f"   🐌 Average slow Lua script: {avg_slow_time:.1f}ms")
        print(f"   🐌 Average KEYS operation: {avg_keys_time:.1f}ms")
        print(f"   ✅ Average GET operation: {string_time / 100 * 1000:.2f}ms")
        print(f"   ✅ Average HGETALL operation: {hash_time / 50 * 1000:.2f}ms")

        if avg_slow_time > 50:
            print("   🚨 SLOW OPERATIONS DETECTED - These should appear in Redis slowlog!")

        # Check slowlog to verify our slow operations were recorded
        try:
            slowlog_entries = self.redis_client.slowlog_get(10)
            print(f"   📋 Current slowlog contains {len(slowlog_entries)} entries")

            if slowlog_entries:
                latest_entry = slowlog_entries[0]
                duration_us = latest_entry.get("duration", 0)
                command = " ".join(latest_entry.get("command", []))[:50] + "..."
                print(f"   🐌 Latest slow command: {command} ({duration_us}μs)")
        except Exception as e:
            print(f"   Warning: Could not check slowlog: {e}")

        # Run diagnostics and agent consultation with comprehensive performance data
        slowlog_count = 0
        try:
            slowlog_entries = self.redis_client.slowlog_get(10)
            slowlog_count = len(slowlog_entries)
        except Exception:
            pass

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Performance Analysis",
                f"Redis with slow operations: Lua scripts avg {avg_slow_time:.1f}ms, KEYS avg {avg_keys_time:.1f}ms, {slowlog_count} slowlog entries",
            )
        else:
            await self._run_diagnostics_and_agent_query(
                f"Application performance issues reported. Performance analysis shows: slow Lua operations averaging {avg_slow_time:.1f}ms, KEYS operations averaging {avg_keys_time:.1f}ms, normal GET operations {string_time / 100 * 1000:.2f}ms, HGETALL operations {hash_time / 50 * 1000:.2f}ms. Slowlog contains {slowlog_count} entries. Please analyze the performance issues and provide optimization recommendations."
            )

        # Cleanup
        self.print_step(4, "Cleaning up performance test data")
        perf_keys = self.redis_client.keys("demo:perf:*")
        if perf_keys:
            # Use UNLINK for better performance on large datasets
            self.redis_client.delete(*perf_keys)
            print(f"   Cleaned up {len(perf_keys)} test keys")

    async def full_health_check(self):
        """Run comprehensive health check and agent consultation."""
        self.print_header("Full Health Check Scenario", "🏥")

        self.print_step(1, "Requesting comprehensive Redis health check from agent")

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Full Health Check",
                f"Redis instance ready for comprehensive health check at {self.redis_url}",
            )
        else:
            # Let the agent run its own comprehensive diagnostics
            await self._run_diagnostics_and_agent_query(
                f"Please perform a complete health check on the Redis instance at {self.redis_url}. "
                f"Provide a comprehensive assessment covering memory usage, connections, performance, "
                f"security, persistence, replication, and any other relevant areas. "
                f"Include recommendations for optimization, security hardening, and best practices."
            )

    async def redis_enterprise_scenario(self):
        """Simulate Redis Enterprise buffer configuration issues."""
        self.print_header("Redis Enterprise Buffer Configuration Scenario", "🏢")

        self.print_step(1, "Setting up Redis Enterprise buffer configuration scenario")

        print("   📋 This scenario simulates a Redis Enterprise database with:")
        print("   • Very low buffer limits (1MB slave_buffer and client_buffer)")
        print("   • Active database with significant memory usage")
        print("   • Potential for buffer overflow and connection issues")
        print()

        # Prepare Enterprise connectivity and register instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            return

        # Optional: baseline memory
        try:
            info = enterprise_client.info("memory")
            used_memory = info.get("used_memory", 0)
            print(f"   📊 Current memory usage: {used_memory / (1024 * 1024):.2f} MB")
        except Exception:
            pass

        self.print_step(2, "Analyzing Redis Enterprise buffer configuration")

        print("   🔍 The Redis Enterprise database has been configured with:")
        print("   • slave_buffer: 1 MB (extremely low)")
        print("   • client_buffer: 1 MB (extremely low)")
        print("   • Database memory usage: ~54 MB")
        print("   • This creates risk of buffer overflows and connection drops")
        print()

        # Create some load to demonstrate buffer pressure
        print("   🧪 Creating buffer pressure scenario...")

        # Add some data to increase memory pressure
        pipe = enterprise_client.pipeline()
        for i in range(100):
            key = f"enterprise:buffer_test:{i}"
            # Create moderately sized values that could stress buffers
            value = f"buffer_test_data_{i}_" + "x" * 1000  # ~1KB per key
            pipe.set(key, value)
        pipe.execute()

        # Get updated memory info
        updated_info = enterprise_client.info("memory")
        updated_memory = updated_info.get("used_memory", 0)
        print(f"   📊 Updated memory usage: {updated_memory / (1024 * 1024):.2f} MB")

        # Simulate some operations that could stress buffers
        print("   🔄 Simulating operations that stress client/slave buffers...")

        # Large MGET operations (stress client buffers)
        keys_to_get = [f"enterprise:buffer_test:{i}" for i in range(50)]
        large_response = enterprise_client.mget(keys_to_get)
        print(f"   📤 MGET operation returned {len([r for r in large_response if r])} values")

        # SCAN operations (can generate large responses)
        scan_results = []
        cursor = 0
        while True:
            cursor, keys = enterprise_client.scan(cursor, match="enterprise:*", count=100)
            scan_results.extend(keys)
            if cursor == 0:
                break
        print(f"   🔍 SCAN operation found {len(scan_results)} keys")

        self.print_step(3, "Demonstrating buffer-related issues")

        print("   ⚠️  With 1MB buffer limits, the following issues may occur:")
        print("   • Client disconnections during large responses (MGET, SCAN)")
        print("   • Replication lag if slave buffer overflows")
        print("   • Connection timeouts under load")
        print("   • Potential data loss in replication scenarios")
        print()

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Redis Enterprise Buffer Configuration",
                f"Redis Enterprise with constrained buffers (1MB each), {updated_memory / (1024 * 1024):.1f}MB memory usage, {len(scan_results)} keys",
            )
        else:
            # Query the agent about the buffer configuration issue
            await self._run_diagnostics_and_agent_query(
                "We are concerned buffer settings may be too low for the workload on a Redis Enterprise database. Please assess risks and recommend settings."
            )

        # Cleanup test data
        self.print_step(4, "Cleaning up test data")
        test_keys = enterprise_client.keys("enterprise:buffer_test:*")
        if test_keys:
            enterprise_client.delete(*test_keys)
            print(f"   🧹 Cleaned up {len(test_keys)} test keys")

        print("   ✅ Redis Enterprise scenario completed")
        print("   💡 In production, consider increasing buffer limits to 32MB+ for slave_buffer")
        print("   💡 and 16MB+ for client_buffer based on workload requirements")

    async def redis_enterprise_maintenance_scenario(self):
        """Simulate Redis Enterprise node stuck in maintenance mode."""
        self.print_header("Redis Enterprise Node Maintenance Mode Scenario", "🔧")

        self.print_step(1, "Checking Redis Enterprise cluster setup")

        print("   📋 This scenario requires a multi-node Redis Enterprise cluster")
        print("   📋 to demonstrate actual maintenance mode.")
        print()
        print("   ⚙️  Prerequisites:")
        print("   1. Start Redis Enterprise nodes:")
        print(
            "      docker-compose up -d redis-enterprise-node1 redis-enterprise-node2 redis-enterprise-node3"
        )
        print()
        print("   2. Initialize the cluster:")
        print("      ./scripts/setup_redis_enterprise_cluster.sh")
        print()
        print("   💡 If you haven't done this yet, press Ctrl+C and run the setup commands above.")
        print()

        # Give user a moment to read
        import time

        time.sleep(2)

        # Connect and register Enterprise instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            return

        self.print_step(2, "Putting node 2 in maintenance mode")

        print("   🔧 Attempting to place Redis Enterprise node 2 in maintenance mode...")
        print()

        # Try to put node 2 in maintenance mode
        import subprocess

        try:
            # First check if we have a multi-node cluster
            result = subprocess.run(
                ["docker", "exec", "redis-enterprise-node1", "rladmin", "status", "nodes"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                print("   📊 Current cluster status:")
                print(result.stdout)
                print()

                # Count nodes
                node_count = result.stdout.count("node:")

                if node_count >= 2:
                    print(f"   ✅ Found {node_count}-node cluster")
                    print("   🔧 Placing node 2 in maintenance mode...")
                    print()

                    # Put node 2 in maintenance mode
                    maint_result = subprocess.run(
                        [
                            "docker",
                            "exec",
                            "redis-enterprise-node1",
                            "rladmin",
                            "node",
                            "2",
                            "maintenance_mode",
                            "on",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    if maint_result.returncode == 0:
                        print("   ✅ Node 2 successfully placed in maintenance mode!")
                        print(maint_result.stdout)
                        print()

                        # Verify the change
                        verify_result = subprocess.run(
                            [
                                "docker",
                                "exec",
                                "redis-enterprise-node1",
                                "rladmin",
                                "status",
                                "nodes",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if verify_result.returncode == 0:
                            print("   📊 Updated cluster status:")
                            print(verify_result.stdout)
                            print()

                            # Parse and highlight the maintenance mode status
                            print("   🔍 VERIFICATION:")
                            if "0/0" in verify_result.stdout:
                                print("   ✅ SUCCESS: Node 2 is now in maintenance mode!")
                                print(
                                    "   ✅ Look for 'node:2' with SHARDS showing '0/0' in the output above"
                                )
                                print("   ✅ This means all shards have been migrated away")
                            else:
                                print(
                                    "   ⚠️  Could not confirm maintenance mode - check output above"
                                )
                            print()
                    else:
                        print(
                            f"   ⚠️  Failed to place node in maintenance mode: {maint_result.stderr}"
                        )
                        print(
                            "   💡 This is expected if node 2 doesn't exist or cluster isn't ready"
                        )
                        print()
                else:
                    print(
                        f"   ⚠️  Only {node_count} node(s) found - need at least 2 nodes for maintenance mode"
                    )
                    print(
                        "   💡 Run: ./scripts/setup_redis_enterprise_cluster.sh to create a 3-node cluster"
                    )
                    print()
            else:
                print(f"   ⚠️  Could not get cluster status: {result.stderr}")
                print("   💡 Make sure Redis Enterprise cluster is initialized")
                print()

        except subprocess.TimeoutExpired:
            print("   ⚠️  Command timed out - cluster may not be fully initialized")
            print()
        except Exception as e:
            print(f"   ⚠️  Could not execute rladmin command: {e}")
            print()

        print("   📋 This demo creates a scenario where you can use the agent to investigate")
        print("   📋 a node in maintenance mode. The agent has access to rladmin commands")
        print("   📋 through the get_redis_enterprise_node_status tool.")
        print()
        print("   🔍 The agent will use rladmin commands to check the actual cluster state")
        print("   🔍 and provide recommendations based on what it finds.")
        print()

        # Add some test data to make the scenario more realistic
        pipe = enterprise_client.pipeline()
        for i in range(50):
            key = f"enterprise:maint_test:{i}"
            value = f"data_{i}_" + "x" * 500  # ~500 bytes per key
            pipe.set(key, value)
        pipe.execute()

        # Get memory usage for status message (best-effort)
        try:
            mem_info = enterprise_client.info("memory")
            used_memory = int(mem_info.get("used_memory", 0))
        except Exception:
            used_memory = 0

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            print("🌐 UI MODE: Scenario is ready for investigation")
            print("   Open the UI and start asking the agent questions!")
            print()
            self._wait_for_ui_interaction(
                "Redis Enterprise Node Maintenance Mode",
                f"Node 2 in maintenance mode. Database active with {used_memory / (1024 * 1024):.1f}MB. Ask agent to investigate!",
            )
            return  # Leave scenario in place for UI interaction

        # CLI mode: Query the agent - it will use its tools to check the cluster status
        query = """Investigate this Redis Enterprise cluster:
            1. Check the overall cluster health.
            2. If you find any issues, provide recommendations for investigation and remediation.
        """

        await self._run_diagnostics_and_agent_query(query)

        # Note: We don't clean up the test data here to leave the scenario in place
        print()
        print("   ✅ Redis Enterprise maintenance mode scenario setup completed")
        print()
        print("   💡 Test data left in place - to clean up:")
        print(
            "   💡 redis-cli -h localhost -p 12000 -a admin --scan --pattern 'enterprise:maint_test:*' | xargs redis-cli -h localhost -p 12000 -a admin DEL"
        )

    async def redis_enterprise_lua_latency_scenario(self):
        """Simulate Redis Enterprise database with Lua script causing high latency."""
        self.print_header("Redis Enterprise Lua Script High Latency Scenario", "🐌")

        self.print_step(1, "Setting up Redis Enterprise Lua latency scenario")

        print("   📋 This scenario simulates a Redis Enterprise database with:")
        print("   • Lua script causing high latency")
        print("   • CPU-intensive operations blocking Redis")
        print("   • Slow operations appearing in slowlog")
        print("   • Performance degradation affecting all operations")
        print()

        # Connect and register Enterprise instance for agent tools
        enterprise_client = await self._prepare_enterprise()
        if not enterprise_client:
            return

        self.print_step(2, "Creating test data and problematic Lua script")

        # Create test data
        print("   Creating test data structures...")
        pipe = enterprise_client.pipeline()
        for i in range(200):
            key = f"enterprise:lua_test:string:{i}"
            value = f"value_{i}_{random.randint(1000, 9999)}"
            pipe.set(key, value)
        pipe.execute()
        print("   ✅ Created 200 test keys")

        # Create a problematic Lua script that causes high latency
        problematic_lua_script = """
        -- Problematic Lua script with CPU-intensive operations
        local iterations = tonumber(ARGV[1]) or 200000
        local key_prefix = ARGV[2] or "enterprise:lua_test"

        -- CPU-intensive computation (blocks Redis)
        local result = 0
        for i = 1, iterations do
            for j = 1, 150 do
                result = result + (i * j) % 1000
                -- Additional computation to increase latency
                local temp = math.sqrt(i * j)
                result = result + math.floor(temp)
            end
        end

        -- Multiple Redis operations that compound the latency
        local keys_processed = 0
        for i = 1, 20 do
            local key = key_prefix .. ":string:" .. i
            local value = redis.call('GET', key)
            if value then
                -- Unnecessary computation on each value
                redis.call('SET', key .. ":processed", value .. "_" .. result)
                keys_processed = keys_processed + 1
            end
        end

        -- More unnecessary operations
        for i = 1, 10 do
            redis.call('SET', 'temp:lua:' .. i, 'processing_' .. result .. '_' .. i)
            redis.call('GET', 'temp:lua:' .. i)
            redis.call('DEL', 'temp:lua:' .. i)
        end

        return {result, keys_processed, "completed"}
        """

        self.print_step(3, "Executing problematic Lua script to generate high latency")

        print("   🐌 Running CPU-intensive Lua script multiple times...")
        print("   ⚠️  This will cause significant latency and block Redis operations")
        print()

        lua_times = []
        for i in range(5):
            try:
                print(f"   Executing slow Lua operation {i + 1}/5...")
                start_time = time.time()
                # Execute the problematic script with high iteration count
                result = enterprise_client.eval(
                    problematic_lua_script, 0, str(100000 + i * 20000), "enterprise:lua_test"
                )
                duration = time.time() - start_time
                lua_times.append(duration * 1000)  # Convert to milliseconds
                print(
                    f"   Lua operation {i + 1} completed in {duration * 1000:.1f}ms (result: {result})"
                )
                time.sleep(0.3)  # Brief pause between operations
            except Exception as e:
                print(f"   Warning: Lua operation {i + 1} failed: {e}")

        # Test normal operations to show the contrast
        print("\n   Testing normal operations for comparison...")
        start_time = time.time()
        for i in range(100):
            enterprise_client.get(f"enterprise:lua_test:string:{i}")
        normal_time = time.time() - start_time
        print(
            f"   100 GET operations: {normal_time:.3f} seconds ({normal_time / 100 * 1000:.2f}ms avg)"
        )

        # Show performance comparison
        avg_lua_time = sum(lua_times) / len(lua_times) if lua_times else 0

        print("\n   📊 Performance Summary:")
        print(f"   🐌 Average Lua script execution: {avg_lua_time:.1f}ms")
        print(f"   ✅ Average GET operation: {normal_time / 100 * 1000:.2f}ms")
        print(f"   📈 Lua script is {avg_lua_time / (normal_time / 100 * 1000):.1f}x slower")

        if avg_lua_time > 100:
            print("   🚨 SEVERE LATENCY DETECTED - Lua script is blocking Redis!")

        # Check slowlog
        try:
            slowlog_entries = enterprise_client.slowlog_get(10)
            print(f"\n   📋 Slowlog contains {len(slowlog_entries)} entries")

            if slowlog_entries:
                print("   Recent slow operations:")
                for idx, entry in enumerate(slowlog_entries[:3], 1):
                    duration_us = entry.get("duration", 0)
                    duration_ms = duration_us / 1000
                    command = " ".join(str(arg) for arg in entry.get("command", [])[:5])
                    if len(command) > 60:
                        command = command[:60] + "..."
                    print(f"   {idx}. {duration_ms:.1f}ms - {command}")
        except Exception as e:
            print(f"   ⚠️  Could not retrieve slowlog: {e}")

        # Handle UI mode vs CLI mode
        if self.ui_mode:
            self._wait_for_ui_interaction(
                "Redis Enterprise Lua Script Latency",
                f"Lua script causing {avg_lua_time:.1f}ms average latency, blocking Redis operations",
            )
            return  # Leave scenario in place for UI interaction

        # CLI mode: Query the agent about the Lua latency issue
        await self._run_diagnostics_and_agent_query(
            "We are seeing slow commands and elevated latency on a Redis Enterprise database. Please investigate and recommend fixes."
        )

        # Cleanup test data
        print("   🧹 Cleaning up test data...")
        test_keys = enterprise_client.keys("enterprise:lua_test:*")
        if test_keys:
            enterprise_client.delete(*test_keys)
            print(f"   ✅ Cleaned up {len(test_keys)} test keys")

        print("\n   ✅ Redis Enterprise Lua latency scenario completed")
        print("   💡 In production, always test Lua scripts under load before deployment")
        print("   💡 Consider using Redis modules or moving complex logic to application layer")

    async def _run_diagnostics_and_agent_query(self, query: str):
        """Run diagnostics and query the SRE agent via Task interface.

        Also attempts to select an appropriate Redis instance automatically so the
        agent doesn't need to ask which one to use.
        """
        self.print_step(4, "Consulting SRE Agent for expert analysis")

        try:
            print("   🤖 Creating task and streaming progress...")
            rc = get_redis_client()

            # Attempt to choose an instance automatically
            selected_instance_id = None
            selected_instance_name = None
            try:
                instances = await get_instances()
                ql = query.lower()

                def pick_enterprise_instance():
                    for inst in instances:
                        name = (inst.name or "").lower()
                        url = inst.connection_url.get_secret_value()
                        if (
                            "enterprise" in name
                            or (
                                getattr(inst.instance_type, "value", inst.instance_type) or ""
                            ).lower()
                            == "redis_enterprise"
                            or ":12000" in url
                            or "redis-enterprise" in url
                        ):
                            return inst
                    return None

                def pick_demo_instance():
                    # Prefer the demo scenarios instance we register
                    for inst in instances:
                        if inst.name == "Demo Redis (Scenarios)":
                            return inst
                    # Secondary: match by docker internal URL
                    agent_url = "redis://redis-demo:6379/0"
                    for inst in instances:
                        try:
                            if inst.connection_url.get_secret_value() == agent_url:
                                return inst
                        except Exception:
                            continue
                    # Fallback: match by host view URL (localhost:7844)
                    for inst in instances:
                        try:
                            if (
                                self.redis_url
                                and inst.connection_url.get_secret_value() == self.redis_url
                            ):
                                return inst
                        except Exception:
                            continue
                    return None

                if "redis enterprise" in ql or "enterprise" in ql:
                    inst = pick_enterprise_instance()
                else:
                    inst = pick_demo_instance()

                if inst:
                    selected_instance_id = inst.id
                    selected_instance_name = inst.name
            except Exception:
                # Best-effort instance selection; continue without if it fails
                pass

            # Prepare context with selected instance and log label hints (non-invasive guidance)
            context = {"instance_id": selected_instance_id} if selected_instance_id else {}
            # Provide gentle hints for Loki selectors so the agent can scope queries to demo streams
            # The agent may or may not use these; they are advisory context only.
            context["log_label_hints"] = {
                "prefer_streams": [
                    {"job": "node-exporter", "instance": "demo-host"},
                    {"job": "docker", "host": "docker-desktop"},
                    {"job": "redis-demo"},
                ],
                "keywords": ["kswapd", "oom-killer", "page allocation failure", "Out of memory"],
            }
            if selected_instance_name:
                print(
                    f"   📎 Using Redis instance: {selected_instance_name} ({selected_instance_id})"
                )

            # Create a new task for this query; thread created automatically if needed
            task_info = await create_task(message=query.strip(), context=context, redis_client=rc)
            task_id = task_info["task_id"]
            thread_id = task_info["thread_id"]
            print(f"   📌 Task ID: {task_id} | Thread ID: {thread_id}")

            tm = TaskManager(redis_client=rc)
            last_seen = 0
            response_text = None

            # Poll for updates until DONE/FAILED
            while True:
                state = await tm.get_task_state(task_id)
                if state and state.updates:
                    for upd in state.updates[last_seen:]:
                        print(f"   • {upd.update_type}: {upd.message}")
                    last_seen = len(state.updates)

                if state and state.status in (TaskStatus.DONE, TaskStatus.FAILED):
                    if state.result and isinstance(state.result, dict):
                        response_text = state.result.get("response") or state.result.get("message")
                    if state.error_message:
                        print(f"   ⚠️ Task error: {state.error_message}")
                    break

                await asyncio.sleep(0.5)

            if response_text:
                try:
                    from rich.console import Console
                    from rich.markdown import Markdown

                    console = Console()
                    console.print("\n" + "=" * 60)
                    console.print("[bold]🤖 SRE Agent Analysis & Recommendations[/bold]")
                    console.print(Markdown(str(response_text)))
                    console.print("=" * 60)
                except Exception:
                    # Fallback to plain text if Rich is unavailable or rendering fails
                    print("\n" + "=" * 60)
                    print("🤖 SRE Agent Analysis & Recommendations")
                    print("=" * 60)
                    print(response_text)
                    print("=" * 60)
            else:
                print("   ℹ️ No response text returned by agent.")

        except Exception as e:
            print(f"   ⚠️  Agent task failed: {str(e)}")
            print("   This might be due to missing OpenAI API key, Redis, or network issues.")

            # Provide fallback guidance based on scenario
            print("\n📋 Fallback Recommendations:")
            print("-" * 40)
            if "memory" in query.lower():
                print("1. Monitor memory usage with INFO memory")
                print("2. Set maxmemory and eviction policy if not configured")
                print("3. Use MEMORY USAGE to identify large keys")
                print("4. Consider data structure optimization")
            elif "connection" in query.lower():
                print("1. Monitor connection count with INFO clients")
                print("2. Review maxclients configuration")
                print("3. Implement connection pooling in applications")
                print("4. Set timeout for idle connections")
            elif "performance" in query.lower():
                print("1. Use SLOWLOG to identify slow commands")
                print("2. Avoid KEYS command in production")
                print("3. Optimize data structures and query patterns")
                print("4. Monitor command statistics with INFO commandstats")
            else:
                print("1. Regular health checks with INFO command")
                print("2. Monitor key metrics: memory, connections, performance")
                print("3. Implement proper security measures")
                print("4. Set up monitoring and alerting")

    async def run_interactive_demo(
        self, auto_run: bool = False, specific_scenario: Optional[str] = None
    ):
        """Run the interactive demo."""
        if not await self.setup_redis_connection():
            return

        if specific_scenario:
            if specific_scenario in self.scenarios:
                await self.scenarios[specific_scenario]()
            else:
                print(f"❌ Unknown scenario: {specific_scenario}")
                print(f"Available scenarios: {list(self.scenarios.keys())}")
            return

        if auto_run:
            # Run all scenarios automatically
            for name, scenario_func in self.scenarios.items():
                print(f"\n{'=' * 20} Running {name.title()} Scenario {'=' * 20}")
                await scenario_func()
                if name != list(self.scenarios.keys())[-1]:  # Don't wait after last scenario
                    print("\n⏸️  Pausing 3 seconds before next scenario...")
                    time.sleep(3)

            print("\n✅ All scenarios completed!")
            return

        # Interactive mode
        while True:
            choice = self.show_main_menu()

            if choice == "0":
                print("\n👋 Thank you for trying the Redis SRE Agent demo!")
                break
            elif choice == str(len(self.menu_items) + 1):
                print("\n🚀 Running all scenarios...")
                for idx, (sid, label, scenario_func) in enumerate(self.menu_items, start=1):
                    print(f"\n{'=' * 10} {sid} - {label} {'=' * 10}")
                    await scenario_func()
                    if idx < len(self.menu_items):
                        print("\n⏸️  Pausing 2 seconds before next scenario...")
                        time.sleep(2)
                print("\n✅ All scenarios completed!")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(self.menu_items):
                        _sid, _label, func = self.menu_items[idx]
                        await func()
                except Exception as e:
                    print(f"❌ Failed to run scenario: {e}")

            # Ask if user wants to continue
            if choice in [str(i) for i in range(1, len(self.menu_items) + 2)]:
                print("\n" + "-" * 60)
                try:
                    continue_choice = (
                        input("Continue with another scenario? (y/n): ").strip().lower()
                    )
                    if continue_choice not in ["y", "yes"]:
                        print("\n👋 Thank you for trying the Redis SRE Agent demo!")
                        break
                except KeyboardInterrupt:
                    print("\n👋 Demo interrupted by user")
                    break


async def main():
    """Main entry point for the demo."""
    parser = argparse.ArgumentParser(description="Redis SRE Agent Interactive Demo")
    parser.add_argument(
        "--scenario",
        help=(
            "Run a specific scenario by ID (e.g., '3.2') or short name "
            "(e.g., 'connection exhaustion', 'redis network saturation', or 'all')"
        ),
    )
    parser.add_argument(
        "--auto-run", action="store_true", help="Run all scenarios automatically without user input"
    )
    parser.add_argument(
        "--ui", action="store_true", help="Use web UI instead of CLI for agent interaction"
    )

    args = parser.parse_args()

    demo = RedisSREDemo(ui_mode=args.ui)

    # If a specific scenario is requested, run it then exit
    if args.scenario:
        func = demo.get_scenario_func(args.scenario)
        if func == "__ALL__":
            if not await demo.setup_redis_connection():
                return
            for _sid, _label, f in demo.menu_items:
                await f()
            return
        if callable(func):
            if not await demo.setup_redis_connection():
                return
            await func()
            return
        print(f"Unknown scenario selector: {args.scenario}")
        # Show some examples to help the user
        print("Try one of:")
        print(" - 1.1")
        print(" - redis network saturation")
        print(" - connection exhaustion")
        return

    # Auto-run all if requested
    if args.auto_run:
        if not await demo.setup_redis_connection():
            return
        for _sid, _label, func in demo.menu_items:
            await func()
        return

    # Otherwise run interactive menu (CLI)
    if not await demo.setup_redis_connection():
        return
    while True:
        choice = demo.show_main_menu()
        # Dispatch handled inside demo loop (requires instance methods) via show_main_menu consumer above
        # We re-use the same logic by delegating to the instance method handler
        # Simulate one cycle by mapping choice into the same handler code
        if choice == "0":
            print("\n\U0001f44b Thank you for trying the Redis SRE Agent demo!")
            break
        elif choice == str(len(demo.menu_items) + 1):
            print("\n\U0001f680 Running all scenarios...")
            for idx, (_sid, label, func) in enumerate(demo.menu_items, start=1):
                print(f"\n{'=' * 10} {label} {'=' * 10}")
                await func()
                if idx < len(demo.menu_items):
                    print("\n\u23f8\ufe0f  Pausing 2 seconds before next scenario...")
                    time.sleep(2)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(demo.menu_items):
                    _sid, _label, func = demo.menu_items[idx]
                    await func()
            except Exception as e:
                print(f"\u274c Failed to run scenario: {e}")


if __name__ == "__main__":
    asyncio.run(main())
