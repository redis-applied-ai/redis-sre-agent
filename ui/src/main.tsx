import React, { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "react-oidc-context";
import { ThemeProvider } from "@radar/ui-kit";
import App from "./App";
import { isAuthEnabled, oidcConfig } from "./auth/oidcConfig";
import { installAuthFetch } from "./auth/authFetch";
import { AuthSync, RequireAuth } from "./auth/AuthSync";

// Import styles (includes UI Kit styles)
import "./index.css";

// Attach the bearer token to API fetches (no-op until a token is available).
installAuthFetch();

// Error boundary component
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error?: Error }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "20px", color: "red" }}>
          <h2>Something went wrong with the App!</h2>
          <pre>{this.state.error?.message}</pre>
          <pre>{this.state.error?.stack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

// Wrap in OIDC auth when configured; otherwise run open (backward compatible).
const AppTree = isAuthEnabled ? (
  <AuthProvider {...oidcConfig}>
    <AuthSync />
    <RequireAuth>
      <App />
    </RequireAuth>
  </AuthProvider>
) : (
  <App />
);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="system">
      <BrowserRouter>
        <ErrorBoundary>{AppTree}</ErrorBoundary>
      </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
