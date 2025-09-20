import { useLocation } from 'react-router-dom';
import type { NavigationItem, DropdownMenuItem } from '@radar/ui-kit';

export const useApp = () => {
  const location = useLocation();

  const currentUser = {
    name: 'John Doe',
    email: 'john.doe@example.com',
    role: 'Admin'
  };

  const navigationItems: NavigationItem[] = [
    {
      label: 'Dashboard',
      href: '/',
      isActive: location.pathname === '/'
    },
    {
      label: 'Users',
      href: '/users',
      isActive: location.pathname === '/users'
    },
    {
      label: 'Deployments',
      href: '/deployments',
      isActive: location.pathname === '/deployments'
    },
    {
      label: 'Tables',
      href: '/tables',
      isActive: location.pathname === '/tables'
    },
    {
      label: 'Forms',
      href: '/forms',
      isActive: location.pathname === '/forms'
    },
    {
      label: 'Charts',
      href: '/charts',
      isActive: location.pathname === '/charts'
    },
    {
      label: 'Modals',
      href: '/modals',
      isActive: location.pathname === '/modals'
    },
    {
      label: 'Notifications',
      href: '/notifications',
      isActive: location.pathname === '/notifications'
    },
    {
      label: 'API Docs',
      href: '/api-docs',
      isActive: location.pathname === '/api-docs'
    },
    {
      label: 'Responsive',
      href: '/responsive',
      isActive: location.pathname === '/responsive'
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
