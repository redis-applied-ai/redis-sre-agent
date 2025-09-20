import { Routes, Route } from "react-router-dom";
import {
  Layout,
  Header,
  DropdownMenu,
  Avatar,
  ThemeToggle,
} from "@radar/ui-kit";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Settings from "./pages/Settings";
import ApiDocumentation from "./pages/ApiDocumentation";
import Deployments from "./pages/Deployments";
import AdvancedForms from "./pages/AdvancedForms";
import DataVisualization from "./pages/DataVisualization";
import Tables from "./pages/Tables";
import Notifications from "./pages/Notifications";
import Modals from "./pages/Modals";
import ResponsiveDesign from "./pages/ResponsiveDesign";
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
                Radar App
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
        <Route path="/users" element={<Users />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/api-docs" element={<ApiDocumentation />} />
        <Route path="/deployments" element={<Deployments />} />
        <Route path="/forms" element={<AdvancedForms />} />
        <Route path="/charts" element={<DataVisualization />} />
        <Route path="/tables" element={<Tables />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/modals" element={<Modals />} />
        <Route path="/responsive" element={<ResponsiveDesign />} />
      </Routes>
    </Layout>
  );
}

export default App;
