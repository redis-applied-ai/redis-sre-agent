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
import Schedules from "./pages/Schedules";
import Settings from "./pages/Settings";
import { useApp } from "./hooks/useApp";

function App() {
  const { currentUser, navigationItems, userMenuItems } = useApp();

  return (
    <Layout
      header={
        <Header
          logo={
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded bg-redis-blue-03 flex items-center justify-center text-white font-bold text-sm">
                R
              </div>
              <span className="text-redis-dusk-01 font-semibold">
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
    >
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/triage" element={<Triage />} />
        <Route path="/knowledge" element={<Knowledge />} />
        <Route path="/schedules" element={<Schedules />} />
        <Route path="/settings" element={<Settings />} />
        {/* Redirect instances to settings with instances section */}
        <Route path="/instances" element={<Navigate to="/settings?section=instances" replace />} />
      </Routes>
    </Layout>
  );
}

export default App;
