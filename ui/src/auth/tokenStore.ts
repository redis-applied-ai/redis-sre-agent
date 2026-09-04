// Synchronously-readable auth state, shared by the fetch wrapper and the WebSocket
// code (which run outside React and cannot use the useAuth() hook). Kept fresh by
// <AuthSync/>, which mirrors react-oidc-context's user into here on every change.

let _accessToken: string | null = null;
let _signOut: (() => void) | null = null;

export function getAccessToken(): string | null {
  return _accessToken;
}

export function setAccessToken(token: string | null): void {
  _accessToken = token;
}

export function setSignOutHandler(fn: (() => void) | null): void {
  _signOut = fn;
}

/** Trigger provider sign-out (no-op when auth is disabled / not yet wired). */
export function signOut(): void {
  if (_signOut) _signOut();
}
