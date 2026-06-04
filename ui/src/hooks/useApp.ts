import { useLocation } from "react-router-dom";
import type { NavigationItem, DropdownMenuItem } from "@radar/ui-kit";

export const useApp = () => {
  const location = useLocation();

  const currentUser = {
    name: "SRE Admin",
    email: "sre@redis.com",
    role: "Site Reliability Engineer",
  };

  const navigationItems: NavigationItem[] = [
    {
      label: "Dashboard",
      href: "/",
      isActive: location.pathname === "/",
    },
    {
      label: "Chat",
      href: "/chat",
      isActive:
        location.pathname === "/chat" || location.pathname === "/triage",
    },
    {
      label: "Knowledge",
      href: "/knowledge",
      isActive: location.pathname.startsWith("/knowledge"),
    },
    {
      label: "Schedules",
      href: "/schedules",
      isActive: location.pathname === "/schedules",
    },
    {
      label: "Settings",
      href: "/settings",
      isActive:
        location.pathname === "/settings" ||
        location.pathname === "/instances" ||
        location.pathname === "/clusters",
    },
  ];

  const userMenuItems: DropdownMenuItem[] = [
    {
      label: "Profile",
      onClick: () => alert("Profile clicked"),
    },
    {
      label: "Account Settings",
      href: "/settings",
    },
    {
      label: "Sign Out",
      onClick: () => alert("Signing out..."),
      variant: "destructive",
    },
  ];

  return {
    currentUser,
    navigationItems,
    userMenuItems,
  };
};
