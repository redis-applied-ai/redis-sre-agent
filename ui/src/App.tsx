import { Routes, Route, Navigate } from "react-router-dom";
import {
  Layout,
  Header,
  DropdownMenu,
  Avatar,
  ThemeToggle,
} from "@radar/ui-kit";
import Dashboard from "./pages/Dashboard";
import Triage from "./pages/Triage";
import Knowledge from "./pages/Knowledge";
import KnowledgeDocumentChunks from "./pages/KnowledgeDocumentChunks";
import Schedules from "./pages/Schedules";
import Settings from "./pages/Settings";
import { useApp } from "./hooks/useApp";

function App() {
  const { currentUser, navigationItems, userMenuItems, schedulesDisabled } =
    useApp();

  return (
    <Layout
      header={
        <Header
          logo={
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded bg-redis-blue-03 flex items-center justify-center text-white font-bold text-sm">
                R
              </div>
              <span className="text-foreground font-semibold">
                Redis SRE Agent
              </span>
            </div>
          }
          navigationItems={navigationItems}
          rightContent={
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <DropdownMenu
                trigger={<Avatar fallback={currentUser.name} size="sm" />}
                items={userMenuItems}
              />
            </div>
          }
        />
      }
      variant="centered"
      contentClassName="app-content-shell"
    >
      <Routes>
        {/* OIDC redirect target: react-oidc-context processes the code before this
            renders (RequireAuth gates on auth), so just hand off into the app. This
            route is what makes the post-login landing work without a manual reload. */}
        <Route path="/callback" element={<Navigate to="/" replace />} />
        <Route path="/" element={<Dashboard />} />
        <Route path="/chat" element={<Triage />} />
        <Route path="/triage" element={<Navigate to="/chat" replace />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route
          path="/knowledge/document-chunks/:documentHash"
          element={<KnowledgeDocumentChunks />}
        />
        <Route
          path="/schedules"
          element={
            schedulesDisabled ? (
              <div className="p-6 text-muted-foreground">
                Scheduling is unavailable while infrastructure authorization is enabled.
              </div>
            ) : (
              <Schedules />
            )
          }
        />
        <Route path="/settings" element={<Settings />} />
        {/* Redirect instances to settings with instances section */}
        <Route
          path="/instances"
          element={<Navigate to="/settings?section=instances" replace />}
        />
        <Route
          path="/clusters"
          element={<Navigate to="/settings?section=clusters" replace />}
        />
      </Routes>
    </Layout>
  );
}

export default App;
