import { useState, useEffect } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Avatar,
  DropdownMenu,
  CollapsibleCard,
  type CollapsibleSection,
  type DropdownMenuItem
} from '@radar/ui-kit';

// Mock data
const mockUsers = [
  { id: 1, name: 'John Doe', email: 'john@example.com', role: 'Admin', status: 'active' },
  { id: 2, name: 'Jane Smith', email: 'jane@example.com', role: 'User', status: 'active' },
  { id: 3, name: 'Bob Johnson', email: 'bob@example.com', role: 'User', status: 'inactive' },
  { id: 4, name: 'Alice Brown', email: 'alice@example.com', role: 'Manager', status: 'active' }
];

const mockStats = [
  { label: 'Total Users', value: '2,847', change: '+12%', icon: '👥' },
  { label: 'Active Sessions', value: '1,254', change: '+8%', icon: '📊' },
  { label: 'Revenue', value: '$52.4K', change: '+15%', icon: '💰' },
  { label: 'Conversion Rate', value: '3.2%', change: '-2%', icon: '📈' }
];

// Hook to detect screen size
const useScreenSize = () => {
  const [screenSize, setScreenSize] = useState<'mobile' | 'tablet' | 'desktop'>('desktop');

  useEffect(() => {
    const checkScreenSize = () => {
      if (window.innerWidth < 640) {
        setScreenSize('mobile');
      } else if (window.innerWidth < 1024) {
        setScreenSize('tablet');
      } else {
        setScreenSize('desktop');
      }
    };

    checkScreenSize();
    window.addEventListener('resize', checkScreenSize);
    return () => window.removeEventListener('resize', checkScreenSize);
  }, []);

  return screenSize;
};

// Responsive Grid Component
const ResponsiveGrid = ({ children, className = '' }: { children: React.ReactNode, className?: string }) => (
  <div className={`
    grid gap-4
    grid-cols-1
    sm:grid-cols-2
    lg:grid-cols-3
    xl:grid-cols-4
    ${className}
  `}>
    {children}
  </div>
);

// Mobile-First Card Component
const MobileCard = ({ title, value, change, icon }: { title: string, value: string, change: string, icon: string }) => (
  <Card className="hover:shadow-lg transition-shadow">
    <CardContent>
      {/* Mobile Layout (default) */}
      <div className="flex items-center justify-between sm:block">
        <div className="flex items-center gap-3 sm:justify-between sm:mb-2">
          <span className="text-2xl">{icon}</span>
          <div className="sm:text-right">
            <span className={`text-xs font-medium px-2 py-1 rounded ${
              change.startsWith('+') ? 'text-redis-green bg-redis-green/20' : 'text-redis-red bg-redis-red/20'
            }`}>
              {change}
            </span>
          </div>
        </div>
        <div className="text-right sm:text-left">
          <div className="text-redis-lg font-bold text-redis-dusk-01">{value}</div>
          <div className="text-redis-xs text-redis-dusk-04">{title}</div>
        </div>
      </div>
    </CardContent>
  </Card>
);

// Responsive Table Component
const ResponsiveTable = () => {
  const screenSize = useScreenSize();

  const getUserActions = (user: any): DropdownMenuItem[] => [
    { label: 'View Profile', onClick: () => alert(`Viewing ${user.name}`) },
    { label: 'Edit User', onClick: () => alert(`Editing ${user.name}`) },
    { label: 'Delete User', onClick: () => alert(`Deleting ${user.name}`), variant: 'destructive' }
  ];

  if (screenSize === 'mobile') {
    // Mobile: Card-based layout
    return (
      <div className="space-y-3">
        {mockUsers.map((user) => (
          <Card key={user.id} className="hover:shadow-md transition-shadow">
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Avatar fallback={user.name} size="sm" />
                  <div>
                    <div className="text-redis-sm font-medium text-redis-dusk-01">
                      {user.name}
                    </div>
                    <div className="text-redis-xs text-redis-dusk-04">
                      {user.email}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                    user.status === 'active'
                      ? 'text-redis-green bg-redis-green/20'
                      : 'text-redis-dusk-04 bg-redis-dusk-07'
                  }`}>
                    {user.status}
                  </span>
                  <DropdownMenu
                    trigger={
                      <Button variant="ghost" size="sm">
                        <span className="text-redis-dusk-04">⋯</span>
                      </Button>
                    }
                    items={getUserActions(user)}
                    placement="bottom-right"
                  />
                </div>
              </div>
              <div className="mt-2 pt-2 border-t border-redis-dusk-08">
                <span className="text-redis-xs text-redis-dusk-04">
                  Role: <span className="text-redis-dusk-01 font-medium">{user.role}</span>
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  // Tablet/Desktop: Traditional table layout
  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-redis-dusk-09 border-b border-redis-dusk-08">
              <tr>
                <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">USER</th>
                <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">ROLE</th>
                <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">STATUS</th>
                <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-redis-dusk-08">
              {mockUsers.map((user) => (
                <tr key={user.id} className="hover:bg-redis-dusk-09 transition-colors">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      <Avatar fallback={user.name} size="sm" />
                      <div>
                        <div className="text-redis-sm font-medium text-redis-dusk-01">
                          {user.name}
                        </div>
                        <div className="text-redis-xs text-redis-dusk-04">
                          {user.email}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="p-4">
                    <span className="text-redis-sm text-redis-dusk-04">{user.role}</span>
                  </td>
                  <td className="p-4">
                    <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                      user.status === 'active'
                        ? 'text-redis-green bg-redis-green/20'
                        : 'text-redis-dusk-04 bg-redis-dusk-07'
                    }`}>
                      {user.status}
                    </span>
                  </td>
                  <td className="p-4">
                    <DropdownMenu
                      trigger={
                        <Button variant="ghost" size="sm">
                          <span className="text-redis-dusk-04">⋯</span>
                        </Button>
                      }
                      items={getUserActions(user)}
                      placement="bottom-right"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

// Responsive Navigation Component
const ResponsiveNav = () => {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <nav className="bg-redis-dusk-09 border-b border-redis-dusk-08">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="h-8 w-8 rounded bg-redis-blue-03 flex items-center justify-center text-white font-bold text-sm">
                R
              </div>
            </div>

            {/* Desktop Navigation */}
            <div className="hidden md:ml-6 md:flex md:space-x-8">
              <a href="#" className="text-redis-dusk-01 hover:text-redis-blue-03 px-3 py-2 text-sm font-medium">
                Dashboard
              </a>
              <a href="#" className="text-redis-dusk-04 hover:text-redis-dusk-01 px-3 py-2 text-sm font-medium">
                Users
              </a>
              <a href="#" className="text-redis-dusk-04 hover:text-redis-dusk-01 px-3 py-2 text-sm font-medium">
                Settings
              </a>
            </div>
          </div>

          <div className="flex items-center">
            {/* Desktop Actions */}
            <div className="hidden md:flex md:items-center md:space-x-4">
              <Button variant="outline" size="sm">
                Export
              </Button>
              <Button variant="primary" size="sm">
                Add User
              </Button>
            </div>

            {/* Mobile menu button */}
            <div className="md:hidden">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              >
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </Button>
            </div>
          </div>
        </div>

        {/* Mobile Navigation Menu */}
        {isMobileMenuOpen && (
          <div className="md:hidden border-t border-redis-dusk-08">
            <div className="px-2 pt-2 pb-3 space-y-1">
              <a href="#" className="text-redis-dusk-01 block px-3 py-2 text-base font-medium">
                Dashboard
              </a>
              <a href="#" className="text-redis-dusk-04 hover:text-redis-dusk-01 block px-3 py-2 text-base font-medium">
                Users
              </a>
              <a href="#" className="text-redis-dusk-04 hover:text-redis-dusk-01 block px-3 py-2 text-base font-medium">
                Settings
              </a>
            </div>
            <div className="pt-4 pb-3 border-t border-redis-dusk-08">
              <div className="flex items-center px-5 space-y-3 flex-col">
                <Button variant="outline" size="sm" className="w-full">
                  Export
                </Button>
                <Button variant="primary" size="sm" className="w-full">
                  Add User
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </nav>
  );
};

const ResponsiveDesign = () => {
  const screenSize = useScreenSize();

  const mobileFirstSection: CollapsibleSection = {
    id: 'mobile-first',
    title: 'Mobile-First Approach',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            Mobile-First Design Examples
          </h4>
          <div className="text-redis-sm text-redis-dusk-04">
            Current: <span className="font-medium text-redis-blue-03 capitalize">{screenSize}</span>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-4">
              Responsive Statistics Cards
            </h5>
            <p className="text-redis-sm text-redis-dusk-04 mb-4">
              These cards adapt their layout based on screen size. On mobile, they stack vertically with a horizontal layout.
              On larger screens, they use a traditional vertical card layout.
            </p>
            <ResponsiveGrid>
              {mockStats.map((stat, index) => (
                <MobileCard
                  key={index}
                  title={stat.label}
                  value={stat.value}
                  change={stat.change}
                  icon={stat.icon}
                />
              ))}
            </ResponsiveGrid>
          </div>

          <div>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-4">
              Responsive Navigation
            </h5>
            <p className="text-redis-sm text-redis-dusk-04 mb-4">
              This navigation component collapses to a hamburger menu on mobile devices and expands to a full navigation bar on desktop.
            </p>
            <Card>
              <CardContent className="p-0">
                <ResponsiveNav />
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  };

  const adaptiveComponentsSection: CollapsibleSection = {
    id: 'adaptive',
    title: 'Adaptive Components',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Components That Adapt to Screen Size
        </h4>

        <div className="space-y-6">
          <div>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-4">
              Responsive Data Table
            </h5>
            <p className="text-redis-sm text-redis-dusk-04 mb-4">
              This table component automatically switches between a traditional table layout on desktop/tablet
              and a card-based layout on mobile devices for better usability.
            </p>
            <ResponsiveTable />
          </div>

          <div>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-4">
              Responsive Form Layout
            </h5>
            <p className="text-redis-sm text-redis-dusk-04 mb-4">
              Forms adapt their column layout based on available space, stacking fields vertically on mobile.
            </p>
            <Card>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                      First Name
                    </label>
                    <input type="text" className="redis-input-base w-full" placeholder="Enter first name" />
                  </div>
                  <div>
                    <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                      Last Name
                    </label>
                    <input type="text" className="redis-input-base w-full" placeholder="Enter last name" />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                      Email Address
                    </label>
                    <input type="email" className="redis-input-base w-full" placeholder="Enter email address" />
                  </div>
                  <div>
                    <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                      Department
                    </label>
                    <select className="redis-input-base w-full">
                      <option>Engineering</option>
                      <option>Marketing</option>
                      <option>Sales</option>
                      <option>Support</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                      Role
                    </label>
                    <select className="redis-input-base w-full">
                      <option>Admin</option>
                      <option>User</option>
                      <option>Manager</option>
                      <option>Viewer</option>
                    </select>
                  </div>
                </div>
                <div className="flex flex-col sm:flex-row gap-3 mt-6">
                  <Button variant="primary" className="flex-1 sm:flex-initial">
                    Save Changes
                  </Button>
                  <Button variant="outline" className="flex-1 sm:flex-initial">
                    Cancel
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    )
  };

  const breakpointsSection: CollapsibleSection = {
    id: 'breakpoints',
    title: 'Breakpoint System',
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Tailwind CSS Breakpoint System
        </h4>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Standard Breakpoints</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">Mobile</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">&lt; 640px</code>
                </div>
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">Small (sm)</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">≥ 640px</code>
                </div>
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">Medium (md)</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">≥ 768px</code>
                </div>
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">Large (lg)</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">≥ 1024px</code>
                </div>
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">Extra Large (xl)</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">≥ 1280px</code>
                </div>
                <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">2X Large (2xl)</span>
                  <code className="text-redis-xs font-mono text-redis-blue-03">≥ 1536px</code>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Responsive Utilities</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div>
                  <h6 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Grid Columns</h6>
                  <code className="text-redis-xs font-mono bg-redis-dusk-09 p-2 rounded block">
                    grid-cols-1 sm:grid-cols-2 lg:grid-cols-4
                  </code>
                </div>
                <div>
                  <h6 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Flex Direction</h6>
                  <code className="text-redis-xs font-mono bg-redis-dusk-09 p-2 rounded block">
                    flex-col sm:flex-row
                  </code>
                </div>
                <div>
                  <h6 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Text Size</h6>
                  <code className="text-redis-xs font-mono bg-redis-dusk-09 p-2 rounded block">
                    text-sm md:text-base lg:text-lg
                  </code>
                </div>
                <div>
                  <h6 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Padding</h6>
                  <code className="text-redis-xs font-mono bg-redis-dusk-09 p-2 rounded block">
                    p-4 md:p-6 lg:p-8
                  </code>
                </div>
                <div>
                  <h6 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Visibility</h6>
                  <code className="text-redis-xs font-mono bg-redis-dusk-09 p-2 rounded block">
                    hidden md:block
                  </code>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Interactive Breakpoint Demo</h5>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <p className="text-redis-sm text-redis-dusk-04">
                Resize your browser window to see how these elements adapt to different screen sizes.
              </p>

              {/* Responsive Grid Demo */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="p-4 bg-redis-blue-03/20 rounded-redis-sm text-center">
                  <div className="text-redis-sm font-medium text-redis-blue-03">Box 1</div>
                  <div className="text-redis-xs text-redis-dusk-04 mt-1">
                    1 col mobile, 2 tablet, 4 desktop
                  </div>
                </div>
                <div className="p-4 bg-redis-green/20 rounded-redis-sm text-center">
                  <div className="text-redis-sm font-medium text-redis-green">Box 2</div>
                  <div className="text-redis-xs text-redis-dusk-04 mt-1">
                    Responsive grid
                  </div>
                </div>
                <div className="p-4 bg-redis-yellow-500/20 rounded-redis-sm text-center">
                  <div className="text-redis-sm font-medium text-redis-yellow-500">Box 3</div>
                  <div className="text-redis-xs text-redis-dusk-04 mt-1">
                    Auto-adapting
                  </div>
                </div>
                <div className="p-4 bg-redis-red/20 rounded-redis-sm text-center">
                  <div className="text-redis-sm font-medium text-redis-red">Box 4</div>
                  <div className="text-redis-xs text-redis-dusk-04 mt-1">
                    Layout changes
                  </div>
                </div>
              </div>

              {/* Responsive Visibility Demo */}
              <div className="flex flex-wrap gap-2">
                <div className="px-3 py-2 bg-redis-blue-03/20 rounded-redis-sm">
                  <span className="text-redis-sm text-redis-blue-03">Always visible</span>
                </div>
                <div className="px-3 py-2 bg-redis-green/20 rounded-redis-sm hidden sm:block">
                  <span className="text-redis-sm text-redis-green">Hidden on mobile</span>
                </div>
                <div className="px-3 py-2 bg-redis-yellow-500/20 rounded-redis-sm hidden md:block">
                  <span className="text-redis-sm text-redis-yellow-500">Hidden on mobile/tablet</span>
                </div>
                <div className="px-3 py-2 bg-redis-red/20 rounded-redis-sm hidden lg:block">
                  <span className="text-redis-sm text-redis-red">Desktop only</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  };

  const mobileOptimizationSection: CollapsibleSection = {
    id: 'mobile-optimization',
    title: 'Mobile Optimization',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Mobile-Specific Optimizations
        </h4>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Touch-Friendly Elements</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-redis-sm text-redis-dusk-04">
                  Mobile interfaces require larger touch targets (minimum 44px) and appropriate spacing.
                </p>
                <div className="space-y-3">
                  <Button variant="primary" className="w-full h-12">
                    Large Touch Target
                  </Button>
                  <div className="flex gap-3">
                    <Button variant="outline" className="flex-1 h-12">
                      Cancel
                    </Button>
                    <Button variant="primary" className="flex-1 h-12">
                      Confirm
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Mobile Forms</h5>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <p className="text-redis-sm text-redis-dusk-04">
                  Forms optimized for mobile with proper input types and layout.
                </p>
                <div className="space-y-3">
                  <input
                    type="email"
                    className="redis-input-base w-full h-12"
                    placeholder="Email (opens email keyboard)"
                  />
                  <input
                    type="tel"
                    className="redis-input-base w-full h-12"
                    placeholder="Phone (opens number pad)"
                  />
                  <input
                    type="number"
                    className="redis-input-base w-full h-12"
                    placeholder="Number input"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Mobile-First Typography</h5>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="text-2xl sm:text-3xl lg:text-4xl font-bold text-redis-dusk-01">
                Responsive Heading
              </div>
              <div className="text-base sm:text-lg text-redis-dusk-04">
                This text scales up on larger screens for better readability.
              </div>
              <div className="text-sm sm:text-base text-redis-dusk-04">
                Body text that remains readable across all devices with appropriate line height and spacing.
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Mobile Performance Tips</h5>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <h6 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Image optimization</h6>
                <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                  <li>• Use responsive images with srcset</li>
                  <li>• Lazy load images below the fold</li>
                  <li>• Compress images for mobile</li>
                  <li>• Use modern formats (WebP, AVIF)</li>
                </ul>
              </div>
              <div>
                <h6 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Loading Performance</h6>
                <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                  <li>• Minimize JavaScript bundles</li>
                  <li>• Use code splitting for routes</li>
                  <li>• Implement service workers</li>
                  <li>• Optimize critical rendering path</li>
                </ul>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Responsive Design</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Mobile-first responsive design patterns and adaptive components
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2">
          <Button variant="outline" className="w-full sm:w-auto">
            View on Mobile
          </Button>
          <Button variant="primary" className="w-full sm:w-auto">
            Design System
          </Button>
        </div>
      </div>

      {/* Current Screen Size Indicator */}
      <Card className="border-redis-blue-03/30 bg-redis-blue-03/10">
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-redis-sm font-semibold text-redis-blue-03">
                Current Screen Size: <span className="capitalize">{screenSize}</span>
              </h3>
              <p className="text-redis-xs text-redis-dusk-04 mt-1">
                Resize your browser window to see responsive changes in real-time
              </p>
            </div>
            <div className="text-2xl">
              {screenSize === 'mobile' && '📱'}
              {screenSize === 'tablet' && '📱'}
              {screenSize === 'desktop' && '💻'}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Responsive Design Examples */}
      <CollapsibleCard
        title="Responsive Design Examples"
        description="Comprehensive examples of mobile-first responsive design patterns"
        sections={[mobileFirstSection, adaptiveComponentsSection, breakpointsSection, mobileOptimizationSection]}
        defaultExpandedSection="mobile-first"
        allowMultipleExpanded={true}
      />

      {/* Best Practices */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Responsive Design Best Practices</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Design Principles</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Start with mobile design first, then scale up</li>
                <li>• Use flexible layouts with CSS Grid and Flexbox</li>
                <li>• Implement progressive enhancement</li>
                <li>• Test on real devices, not just browser tools</li>
                <li>• Consider touch interactions and gestures</li>
                <li>• Optimize for different screen orientations</li>
                <li>• Use relative units (rem, em, %) over fixed pixels</li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Performance Considerations</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Minimize HTTP requests on mobile networks</li>
                <li>• Use critical CSS for above-the-fold content</li>
                <li>• Implement lazy loading for images and components</li>
                <li>• Optimize JavaScript for mobile devices</li>
                <li>• Use responsive images with appropriate sizes</li>
                <li>• Consider offline functionality with service workers</li>
                <li>• Monitor Core Web Vitals on mobile devices</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default ResponsiveDesign;
