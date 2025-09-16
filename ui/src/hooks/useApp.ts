import { useLocation } from 'react-router-dom';
import type { NavigationItem, DropdownMenuItem } from '@radar/ui-kit';

export const useApp = () => {
  const location = useLocation();

  const currentUser = {
    name: 'SRE Admin',
    email: 'sre@redis.com',
    role: 'Site Reliability Engineer'
  };

  const navigationItems: NavigationItem[] = [
    {
      label: 'Dashboard',
      href: '/',
      isActive: location.pathname === '/'
    },
    {
      label: 'Triage',
      href: '/triage',
      isActive: location.pathname === '/triage'
    },
    {
      label: 'Instances',
      href: '/instances',
      isActive: location.pathname === '/instances'
    },
    {
      label: 'Settings',
      href: '/settings',
      isActive: location.pathname === '/settings'
    }
  ];

  const userMenuItems: DropdownMenuItem[] = [
    {
      label: 'Profile',
      onClick: () => alert('Profile clicked')
    },
    {
      label: 'Account Settings',
      href: '/settings'
    },
    {
      label: 'Sign Out',
      onClick: () => alert('Signing out...'),
      variant: 'destructive'
    }
  ];

  return {
    currentUser,
    navigationItems,
    userMenuItems
  };
};
