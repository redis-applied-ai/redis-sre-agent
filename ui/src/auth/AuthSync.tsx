// React glue for OIDC:
//  - AuthSync mirrors the current access token + a sign-out handler into the module
//    token store so non-React code (fetch wrapper, WebSocket) can read them synchronously.
//  - RequireAuth gates the app: redirects to the provider when unauthenticated.

import { useEffect, type ReactNode } from "react";
import { useAuth } from "react-oidc-context";

import { setAccessToken, setSignOutHandler } from "./tokenStore";

export function AuthSync(): null {
  const auth = useAuth();

  useEffect(() => {
    setAccessToken(auth.user?.access_token ?? null);
  }, [auth.user]);

  useEffect(() => {
    setSignOutHandler(() =>
      auth.signoutRedirect({ post_logout_redirect_uri: window.location.origin }),
    );
    return () => setSignOutHandler(null);
  }, [auth]);

  return null;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const auth = useAuth();

  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated && !auth.activeNavigator && !auth.error) {
      void auth.signinRedirect();
    }
  }, [auth.isLoading, auth.isAuthenticated, auth.activeNavigator, auth.error]);

  if (auth.error) {
    return <div style={{ padding: 20 }}>Authentication error: {auth.error.message}</div>;
  }
  if (auth.isLoading || !auth.isAuthenticated) {
    return <div style={{ padding: 20 }}>Signing in…</div>;
  }
  return <>{children}</>;
}
