// OIDC configuration for the SPA. Discovery-driven (endpoints resolved from the
// issuer's /.well-known/openid-configuration by oidc-client-ts), provider-neutral.
// Auth is enabled only when both issuer and client_id are provided at build time;
// otherwise the app runs in open mode (matches the backend auth_enabled=false default).

import { WebStorageStateStore } from "oidc-client-ts";
import type { AuthProviderProps } from "react-oidc-context";

const env = import.meta.env as Record<string, string | undefined>;

const issuer = env.VITE_OIDC_ISSUER;
const clientId = env.VITE_OIDC_CLIENT_ID;
// Self-deployed: the SPA auto-derives its redirect from wherever it is served,
// so no per-environment build config is needed. Overridable for path-prefix setups.
const redirectUri =
  env.VITE_OIDC_REDIRECT_URI ||
  (typeof window !== "undefined" ? `${window.location.origin}/callback` : undefined);
const scope = env.VITE_OIDC_SCOPE || "openid profile email";

export const isAuthEnabled = Boolean(issuer && clientId);

export const oidcConfig: AuthProviderProps = {
  authority: issuer ?? "",
  client_id: clientId ?? "",
  redirect_uri: redirectUri ?? "",
  post_logout_redirect_uri:
    typeof window !== "undefined" ? window.location.origin : undefined,
  response_type: "code",
  scope,
  automaticSilentRenew: true,
  userStore:
    typeof window !== "undefined"
      ? new WebStorageStateStore({ store: window.sessionStorage })
      : undefined,
  // The access token's audience is requested via `scope` (e.g. api://<id>/access_as_user),
  // not a `resource` query param — Entra's v2 authorize endpoint rejects `resource`.
  // After the provider redirects back to /callback, clean the URL to "/".
  onSigninCallback: () => {
    if (typeof window !== "undefined") {
      window.history.replaceState({}, document.title, "/");
    }
  },
};
