# Authentication (OIDC SSO)

The agent supports **authentication-only** SSO across the Web UI, REST API + WebSockets,
and CLI, using standard OIDC with **Microsoft Entra ID as the default provider**. It is
**provider-neutral**: pointing the config at any OIDC provider (Okta, Auth0, Keycloak,
dex, Ping, Google) works with no code change — everything is driven by the provider's
discovery document.

> **Scope:** identity only (who you are), not authorization (what you may do). MCP server
> auth is deferred. There is **no static/long-lived API-key** path on any surface.

## Default: OFF

Auth is **disabled by default** (`auth_enabled=false`) — the agent runs open, exactly as
before. When you enable it, missing resource config is **fail-closed**: protected routes
return `503` rather than silently serving open.

## Configuration

All settings are flat environment variables (or config-file keys). Set them on the API
service and worker.

| Setting | Required when enabled | Description |
|---|---|---|
| `AUTH_ENABLED` | — | `true` to enforce auth. Default `false` (open mode). |
| `AUTH_ISSUER_URL` | **yes** | OIDC issuer (this alone selects the provider). Discovery is read from `<issuer>/.well-known/openid-configuration`. |
| `AUTH_AUDIENCE` | **yes** | Expected token `aud`. For Entra **v2** tokens this is the API app's bare client-ID GUID (not `api://<id>`) — see the token-gotchas note below. |
| `AUTH_SCOPES` | — | Default `openid profile email`. |
| `AUTH_UI_CLIENT_ID` | for UI login | Public SPA client id (enables UI login). |
| `AUTH_CLI_CLIENT_ID` | for CLI login | Public client id (enables `redis-sre-agent login`). |
| `AUTH_API_CLIENT_ID` | for API browser login | Confidential client id (enables `/auth/login`). |
| `AUTH_API_CLIENT_SECRET` | with `AUTH_API_CLIENT_ID` | Confidential client secret. |
| `AUTH_API_PUBLIC_BASE_URL` | with `AUTH_API_CLIENT_ID` | Public base URL of the API (e.g. `https://sre.acme.com`). Used to build `/auth/callback` and the logout redirect. **Never** derived from request headers. |
| `AUTH_JWKS_CACHE_TTL_SECONDS` | — | Discovery/JWKS cache TTL. Default `3600`. |
| `AUTH_CLOCK_SKEW_LEEWAY_SECONDS` | — | Allowed `exp`/`nbf` skew. Default `60`. |

**Partial registration is first-class.** Each surface's client id is optional and
independent: configure only the surfaces you use. An unconfigured surface disables *its
own* login with a clear message; the others are unaffected.

### UI (SPA) build-time env

The UI reads build-time Vite vars. Auth is enabled in the UI only when issuer + client id
are present; otherwise the UI runs open.

| Vite var | Notes |
|---|---|
| `VITE_OIDC_ISSUER` | Same issuer as `AUTH_ISSUER_URL`. |
| `VITE_OIDC_CLIENT_ID` | The UI (public/PKCE) client id. |
| `VITE_OIDC_AUDIENCE` | Resource/audience for the access token. |
| `VITE_OIDC_SCOPE` | Optional scope override. |
| `VITE_OIDC_REDIRECT_URI` | Optional. Defaults to `window.location.origin + /callback` (auto-adapts to wherever the UI is served — register that origin with your provider). |
| `VITE_API_BASE_URL` | Set when the API is on a different origin so the SPA attaches the bearer to it. |

## Per-surface behavior

- **UI** — auth-code + PKCE redirect to the provider; token in `sessionStorage`; a login
  page + protected routes; the bearer is attached to every API call and the WebSocket
  (via the `bearer` subprotocol). Sign-out clears the session and ends the provider SSO
  session. Silent renew keeps the ~60-minute access token fresh.
- **REST API** — a global dependency validates the bearer on every protected route
  (`401` when missing/invalid, `503` fail-closed when misconfigured). Exempt (no bearer):
  `/`, `/api/v1/`, `/api/v1/health`, `/api/v1/metrics`, `/api/v1/metrics/health`, `/docs`,
  `/openapi.json`, `/auth/*`. **Metrics are exempt — gate `/api/v1/metrics*` behind network
  policy**, and note that infra metrics are then unauthenticated by design.
- **API browser login** — `GET /auth/login` → provider; `GET /auth/callback` exchanges the
  code; `GET /auth/logout` ends the provider session. These are a convenience for humans
  hitting the API directly; the SPA does its own PKCE flow.
- **WebSockets** — the token is validated **before** the socket is accepted, carried on the
  `Sec-WebSocket-Protocol` subprotocol (browsers cannot set an `Authorization` header).
- **CLI** — `redis-sre-agent login` runs the device-code flow (works headless/over SSH),
  caches the token (`~/.config/redis-sre-agent/token.json`, mode 0600), and refreshes it
  silently. `redis-sre-agent logout` clears the cache. Humans only.

### Logout and token revocation caveat

Tokens are stateless bearer JWTs (no server session store). **Logout ends the provider SSO
session, but an already-issued access token remains valid until it expires** (~60 min).
Revoking a token before expiry would require a denylist (a session store), which is out of
scope this phase. The short access-token lifetime is the mitigation.

## Microsoft Entra ID: three app registrations

Register three apps in your single tenant — one per trust profile:

| # | App | Client type | Flow | Redirect URIs |
|---|---|---|---|---|
| 1 | **UI** | Public (SPA) | auth-code + PKCE | `<ui-origin>/callback` |
| 2 | **CLI** | Public | device-code (enable "Allow public client flows") | none |
| 3 | **API** | Confidential (also the resource that defines the audience) | server-side code flow | `AUTH_API_PUBLIC_BASE_URL` + `/auth/callback` |

### Two Entra token gotchas (set these on the API app, or every call 401s)

By default Entra issues **v1** access tokens, whose issuer (`https://sts.windows.net/<tid>/`)
does not match the **v2** issuer this agent discovers from `AUTH_ISSUER_URL`
(`https://login.microsoftonline.com/<tid>/v2.0`) → `bad_issuer`. Fix it on the **API app**:

1. **API app → Manifest → set `"accessTokenAcceptedVersion": 2`** → Save. Now access tokens
   are v2 (issuer `.../v2.0`), matching discovery.
2. **`AUTH_AUDIENCE` = the API app's bare client-ID GUID** (e.g. `80de6531-...`), **not**
   `api://<id>`. This is the coupling that surprises people: a **v1** token's `aud` is the
   App ID URI (`api://<id>`), but a **v2** token's `aud` is the bare client-ID GUID. Since we
   use v2 (step 1), use the GUID.

The UI and CLI request tokens for this API (via the `access_as_user` scope); the resulting
access tokens carry `aud` = the API app's client-ID GUID.

## Swapping providers (portability)

Because everything is discovery-driven, switching providers is **config-only**:

```bash
# Example: point at a Keycloak realm instead of Entra (issuer alone selects the provider)
AUTH_ISSUER_URL=https://keycloak.example.com/realms/sre
AUTH_AUDIENCE=sre-agent
```

This is verified in CI by an integration test that authenticates end-to-end against a local
**dex** container with only config changed (`tests/integration/test_auth_portability.py`,
run with `--run-api-tests`; dex is the `auth` profile in `docker-compose.integration.yml`).

## Health / self-check

`GET /api/v1/health` reports an `auth` block (mode + per-surface enablement + `fail_closed`).
On startup the API logs an advisory self-check; it never gates requests — a transient IdP
outage yields per-request `503`s that auto-recover when discovery returns, with no restart.

## No vendor SDKs

Auth is built on generic OIDC libraries (`authlib` + `pyjwt[crypto]` on the backend,
`oidc-client-ts` + `react-oidc-context` in the UI). No `msal` / `@azure/*` is used.

## Troubleshooting

The API logs a rejection reason on every 401 (`auth reject reason=... path=...`) — check it
first (`docker logs <api-container> | grep 'auth reject'`).

| Reason / symptom | Cause / fix |
|---|---|
| `401 bad_issuer` | Entra issued a **v1** token (`iss=https://sts.windows.net/<tid>/`) but discovery is v2. Set `accessTokenAcceptedVersion: 2` in the **API app** manifest, then get a fresh token. |
| `401 bad_audience` | Token `aud` doesn't match `AUTH_AUDIENCE`. For v2 tokens `AUTH_AUDIENCE` must be the API app's **bare client-ID GUID**, not `api://<id>`. (Also occurs if the UI/CLI didn't request the `access_as_user` scope → token is Graph-audienced.) |
| `401 malformed` | The bearer isn't a valid JWT — usually copy/paste quotes or whitespace around the token (`Bearer "eyJ..."`). Send the raw `eyJ...` value. |
| `401 expired` | Token past its lifetime (default ~60-90 min). Re-authenticate; UI/CLI refresh silently. |
| `503 auth misconfigured` | `AUTH_ISSUER_URL` or `AUTH_AUDIENCE` unset while `AUTH_ENABLED=true`. |
| `503 discovery unavailable` | Issuer unreachable/wrong. Auto-recovers per-request once fixed (no restart). |
| App won't start, `SettingsError ... auth_scopes` | Old build without the list-parse fix; `AUTH_SCOPES` must be comma- or space-separated. |
| `/auth/login` 404 | API surface disabled (`AUTH_API_CLIENT_ID` unset). `503` there → `AUTH_API_PUBLIC_BASE_URL` unset. |
| Entra `redirect_uri mismatch` | The exact redirect URI (`<base>/auth/callback` for API, `<origin>/callback` for UI) isn't registered on that app. |
