# Infrastructure Authorization

Optional **per-principal authorization** that scopes *which clusters and database instances*
an authenticated user may access. It builds on [Authentication (OIDC SSO)](authentication-sso.md):
authn establishes *who you are*, authz decides *what you may act on*.

The agent owns **no** principal-to-target mapping. That decision is delegated to a
**deployment-supplied hook** you configure — the agent calls it every time targets are
resolved or listed, passing the validated token and the candidate targets, and uses the
subset the hook returns.

> **Scope:** clusters and database instances. Schedules are **disabled** while authz is on
> (creation, execution, and the UI surface). MCP **refuses to serve** while authz is on
> (it has no authentication path today).

## Default: OFF

Authz is **disabled by default** (`INFRASTRUCTURE_AUTHORIZATION_ENABLED=false`) and is pure
passthrough when off — zero behavior change. When enabled it is **fail-closed**: no token, a
hook error, or a hook timeout yields an *empty* allowed set (the hook can only remove access,
never grant beyond the registry).

## Configuration

Set these on **both** the API service and the worker (see [Running via Docker](#running-via-docker)).

| Setting | Required when enabled | Description |
|---|---|---|
| `INFRASTRUCTURE_AUTHORIZATION_ENABLED` | — | `true` to enforce authz. Default `false`. |
| `INFRASTRUCTURE_AUTHORIZATION_HOOK` | **yes** | Import path `module:callable` resolving the scope hook (resolved inside the process, not a host file path). |

Authz **requires** authn. If `INFRASTRUCTURE_AUTHORIZATION_ENABLED=true` while
`AUTH_ENABLED=false`, or the hook path is unset, startup **fails** with a clear error — you
can't scope by an identity you haven't verified.

## The hook contract

```python
def scope(auth_token: str, targets):
    # auth_token: the validated JWT bearer STRING (signature/iss/aud/exp already checked).
    #             Decode it, or forward it to an external authz service.
    # targets:    list of TargetRef(kind="cluster"|"instance", resource_id, name, environment)
    # return:     the allowed subset (same objects). Sync or async both work.
    ...
```

- The token is authn-validated **before** the hook runs — the hook never sees an unverified
  token.
- The hook is called **live** on every resolution/listing, so access changes (and
  revocations) take effect on the next turn without re-issuing a token — provided your hook
  reads its source of truth (DB / authz service) on each call rather than caching in memory.
- A hook call is bounded by a 5-second timeout; a slow external service fails closed for that
  call rather than stalling every resolution.

## What enforcement looks like

- **Listing** (`instances list`, cluster/instance APIs, target catalog) scopes *before* it
  counts, so users never see or count inaccessible targets.
- **Explicit reference** to a denied target returns **authorization-denied** — with the
  *same* message as a nonexistent target, so denials aren't an enumeration oracle.
- **Deep-triage** reports any scoped-out targets rather than silently dropping them.

## Which surfaces are scoped

Authorization is enforced at the **API trust boundary** — where the validated token is
established and the scoped loaders (`query_*`, guarded `get_*_by_id`) run. That covers the
**REST API, WebSockets, UI, and the agent** (turns and their tools).

The **CLI's in-process commands** (`instance list/get`, `cluster list/get`) are **not**
scoped: they read Redis directly via the core loaders, without crossing the API boundary or
carrying a principal, so they return the **full registry**. This is intentional — the CLI
already holds the Redis connection (`REDIS_URL`), so anyone who can run it can read Redis
directly regardless. Treat the CLI's in-process commands as an **operator/admin** surface;
authorization scoping applies to the user-facing API/UI/agent surfaces, not to operators who
already have direct infrastructure access.

> **Token cache is per-container.** The CLI caches its token at
> `~/.config/redis-sre-agent/token.json` inside the container's writable layer. Recreating the
> container (`docker compose up --force-recreate`) clears it — you'll need to `login` again.
> Bind-mount `~/.config` or run the CLI on the host if you want the token to persist.

## Running via Docker

The dotted `module:callable` path is resolved by `importlib` **inside the container**, so the
hook module must be importable there, and the settings must reach **both** services that
enforce:

- **`sre-agent`** (API) — sets the token on each request, enforces on listing + base loaders.
- **`sre-worker`** (`redis-sre-agent worker start`) — runs agent turns, enforces on the base
  loaders. It re-validates the token captured at enqueue, so it **also** needs
  `AUTH_ISSUER_URL` / `AUTH_AUDIENCE`.

If the hook is importable in only one service, the other fails closed.

### 1. Make the hook importable in both containers

The compose file bind-mounts `./redis_sre_agent:/app/redis_sre_agent` into both services and
`redis_sre_agent` is an installed package, so the simplest reliable home is **inside the
package** — the file then appears in both containers with no image rebuild:

```bash
# place your hook here (host path); it is live in both containers via the bind mount
cp your_hook.py redis_sre_agent/authz_hook.py
```

Then set `INFRASTRUCTURE_AUTHORIZATION_HOOK=redis_sre_agent.authz_hook:scope`.

A file at the repo root is **not** individually mounted, so it is not reliably present in the
container. If you must keep the hook outside the package, bind-mount the file and put its
directory on `PYTHONPATH`:

```yaml
# docker-compose override, on BOTH sre-agent and sre-worker
volumes:
  - ./my_hook.py:/app/my_hook.py
environment:
  - PYTHONPATH=/app
# INFRASTRUCTURE_AUTHORIZATION_HOOK=my_hook:scope
```

### 2. Set the environment

`.env` is mounted into both services, so adding the vars there covers both — no per-service
edits needed:

```dotenv
# authentication (required by authz)
AUTH_ENABLED=true
AUTH_ISSUER_URL=https://login.example.com/...
AUTH_AUDIENCE=<api-audience>
# authorization
INFRASTRUCTURE_AUTHORIZATION_ENABLED=true
INFRASTRUCTURE_AUTHORIZATION_HOOK=redis_sre_agent.authz_hook:scope
```

Then recreate the services so the new env loads:

```bash
docker compose up -d
docker compose logs sre-agent   # startup fails closed here if authn is off or hook is unset
```

### 3. Reloading hook changes

- `sre-agent` runs `uvicorn --reload` — editing the hook source restarts it automatically.
- `sre-worker` has **no** `--reload` — after editing the hook, run
  `docker compose restart sre-worker` to reload it.

A restart is only needed because the process imports the hook module once. A production hook
that reads its mapping from a DB or authz service on each call needs **no** restart for access
changes — only for changes to the hook code itself.

### Production (baked image)

Ship the hook inside the package (or add a `COPY` for it) and rebuild, set the two
`INFRASTRUCTURE_AUTHORIZATION_*` vars plus the authn config in your deployment environment,
and use the same dotted path. No bind-mount required.
