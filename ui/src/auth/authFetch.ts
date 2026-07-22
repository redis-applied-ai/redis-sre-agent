// One-time global fetch wrapper that attaches the bearer token to API requests.
// The API service issues fetch() from ~40 call sites; wrapping window.fetch once is
// the single choke point without touching each site. The token is only attached to
// same-origin requests and the configured API origin — never to the OIDC provider or
// other third parties (so we never leak the token during discovery/token exchange).

import { getAccessToken } from "./tokenStore";

const env = import.meta.env as Record<string, string | undefined>;
const apiBaseUrl = env.VITE_API_BASE_URL;

function shouldAttach(url: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const target = new URL(url, window.location.href);
    if (target.origin === window.location.origin) return true;
    if (apiBaseUrl) {
      const base = new URL(apiBaseUrl, window.location.href);
      if (target.origin === base.origin) return true;
    }
  } catch {
    // Relative or unparseable URL - treat as same-origin.
    return true;
  }
  return false;
}

let installed = false;

export function installAuthFetch(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const token = getAccessToken();
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input.url;

    if (token && shouldAttach(url)) {
      const headers = new Headers(
        init?.headers ?? (input instanceof Request ? input.headers : undefined),
      );
      if (!headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      init = { ...init, headers };
    }
    return original(input, init);
  };
}
