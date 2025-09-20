import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Loader,
  ErrorMessage,
  Tooltip,
  CollapsibleCard,
  type CollapsibleSection
} from '@radar/ui-kit';

// Mock data
const dashboardStats = [
  { label: 'Total Users', value: 1234, change: '+5.2%', positive: true },
  { label: 'Active Sessions', value: 89, change: '-2.1%', positive: false },
  { label: 'Server Uptime', value: '99.9%', change: '+0.1%', positive: true },
  { label: 'Response Time', value: '45ms', change: '-12ms', positive: true }
];

const recentActivity = [
  { id: 1, action: 'User login', user: 'john.doe@example.com', time: '2 minutes ago' },
  { id: 2, action: 'Configuration updated', user: 'admin@example.com', time: '15 minutes ago' },
  { id: 3, action: 'New deployment created', user: 'sarah.wilson@example.com', time: '1 hour ago' },
  { id: 4, action: 'Database backup completed', user: 'system', time: '2 hours ago' }
];

const Dashboard = () => {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState('');

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setError('');

    // Simulate API call
    setTimeout(() => {
      if (Math.random() > 0.8) {
        setError('Failed to refresh dashboard data. Please try again.');
      }
      setIsRefreshing(false);
    }, 2000);
  };

  const configurationSections: CollapsibleSection[] = [
    {
      id: 'system',
      title: 'System Configuration',
      icon: <div className="h-4 w-4 bg-redis-blue-03 rounded" />,
      content: (
        <div className="p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                Server Port
              </label>
              <input
                type="number"
                defaultValue="3000"
                className="redis-input-base w-full"
              />
            </div>
            <div>
              <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                Environment
              </label>
              <select className="redis-input-base w-full">
                <option>Production</option>
                <option>Staging</option>
                <option>Development</option>
              </select>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'security',
      title: 'Security Settings',
      icon: <div className="h-4 w-4 bg-redis-red rounded" />,
      content: (
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-redis-sm text-redis-dusk-01">Two-Factor Authentication</span>
            <Button variant="outline" size="sm">Configure</Button>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-redis-sm text-redis-dusk-01">API Key Rotation</span>
            <Button variant="outline" size="sm">Enable</Button>
          </div>
        </div>
      )
    }
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Dashboard</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Welcome back! Here's what's happening with your application.
          </p>
        </div>
        <div className="flex gap-2">
          <Tooltip content="Refresh all dashboard data">
            <Button
              variant="outline"
              onClick={handleRefresh}
              isLoading={isRefreshing}
            >
              {isRefreshing ? <Loader size="sm" /> : 'Refresh'}
            </Button>
          </Tooltip>
          <Button variant="primary">New Deployment</Button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <ErrorMessage
          message={error}
          title="Dashboard Error"
        />
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {dashboardStats.map((stat, index) => (
          <Card key={index} className="hover:shadow-lg transition-shadow">
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-redis-xs text-redis-dusk-04 font-medium">
                    {stat.label}
                  </p>
                  <p className="text-redis-lg font-bold text-redis-dusk-01 mt-1">
                    {stat.value}
                  </p>
                </div>
                <div className={`text-redis-xs font-medium ${
                  stat.positive ? 'text-redis-green' : 'text-redis-red'
                }`}>
                  {stat.change}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Recent Activity</h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentActivity.map((activity) => (
                <div key={activity.id} className="flex items-center justify-between p-3 rounded-redis-sm bg-redis-dusk-09">
                  <div>
                    <p className="text-redis-sm font-medium text-redis-dusk-01">
                      {activity.action}
                    </p>
                    <p className="text-redis-xs text-redis-dusk-04">
                      by {activity.user}
                    </p>
                  </div>
                  <span className="text-redis-xs text-redis-dusk-04">
                    {activity.time}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Quick Actions */}
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Quick Actions</h3>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3">
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center gap-2"
                onClick={() => alert('Add User functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-blue-03" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                </svg>
                <span className="text-redis-xs">Add User</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center gap-2"
                onClick={() => alert('Deploy functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-green" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                </svg>
                <span className="text-redis-xs">Deploy</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center gap-2"
                onClick={() => alert('Backup functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-yellow-500" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/>
                </svg>
                <span className="text-redis-xs">Backup</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center gap-2"
                onClick={() => alert('Alerts functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-red" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z"/>
                </svg>
                <span className="text-redis-xs">Alerts</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Configuration Panel */}
      <CollapsibleCard
        title="Configuration"
        description="Manage your application settings and security preferences"
        sections={configurationSections}
        defaultExpandedSection="system"
      />
    </div>
  );
};

export default Dashboard;
