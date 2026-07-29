import { useLocation } from "react-router-dom";
import type { NavigationItem, DropdownMenuItem } from "@radar/ui-kit";
import { isAuthEnabled } from "../auth/oidcConfig";
import { signOut } from "../auth/tokenStore";
import { useInfraAuthzDisabled } from "./useInfraAuthzDisabled";

export const useApp = () => {
  const location = useLocation();
  const schedulesDisabled = useInfraAuthzDisabled();

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
  ].filter((item) => !(schedulesDisabled && item.href === "/schedules"));

  const userMenuItems: DropdownMenuItem[] = [
    {
      label: "Account Settings",
      href: "/settings",
    },
    {
      label: "Sign Out",
      onClick: isAuthEnabled ? () => signOut() : () => alert("Signing out..."),
      variant: "destructive",
    },
  ];

  return {
    currentUser,
    navigationItems,
    userMenuItems,
    schedulesDisabled,
  };
};
