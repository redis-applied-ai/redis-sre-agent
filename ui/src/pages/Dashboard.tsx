import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Loader,
  ErrorMessage,
  Tooltip,
} from '@radar/ui-kit';

// Mock data for Redis SRE Dashboard
const redisStats = [
  { label: 'Redis Instances', value: 12, change: '+2', positive: true },
  { label: 'Active Connections', value: 1847, change: '+5.2%', positive: true },
  { label: 'Memory Usage', value: '78%', change: '-2.1%', positive: true },
  { label: 'Avg Response Time', value: '1.2ms', change: '-0.3ms', positive: true }
];

const recentAlerts = [
  { id: 1, severity: 'warning', message: 'High memory usage on redis-prod-01', time: '5 minutes ago' },
  { id: 2, severity: 'info', message: 'Backup completed successfully', time: '1 hour ago' },
  { id: 3, severity: 'error', message: 'Connection timeout on redis-staging-02', time: '2 hours ago' },
  { id: 4, severity: 'info', message: 'Scheduled maintenance completed', time: '4 hours ago' }
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

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'error': return 'text-redis-red';
      case 'warning': return 'text-redis-yellow-500';
      case 'info': return 'text-redis-blue-03';
      default: return 'text-redis-dusk-04';
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Redis SRE Dashboard</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Monitor your Redis infrastructure and respond to incidents.
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
          <Button variant="primary" onClick={() => window.location.href = '/triage'}>
            Start Triage
          </Button>
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
        {redisStats.map((stat, index) => (
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
        {/* Recent Alerts */}
        <Card>
          <CardHeader>
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Recent Alerts</h3>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {recentAlerts.map((alert) => (
                <div key={alert.id} className="flex items-center justify-between p-3 rounded-redis-sm bg-redis-dusk-09">
                  <div className="flex items-center gap-3">
                    <div className={`h-2 w-2 rounded-full ${
                      alert.severity === 'error' ? 'bg-redis-red' :
                      alert.severity === 'warning' ? 'bg-redis-yellow-500' :
                      'bg-redis-blue-03'
                    }`} />
                    <div>
                      <p className="text-redis-sm font-medium text-redis-dusk-01">
                        {alert.message}
                      </p>
                      <p className={`text-redis-xs ${getSeverityColor(alert.severity)}`}>
                        {alert.severity.toUpperCase()}
                      </p>
                    </div>
                  </div>
                  <span className="text-redis-xs text-redis-dusk-04">
                    {alert.time}
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
                onClick={() => window.location.href = '/triage'}
              >
                <svg className="h-6 w-6 text-redis-blue-03" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h14l4 4V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z"/>
                </svg>
                <span className="text-redis-xs">Start Triage</span>
              </Button>
              <Button
                variant="outline"
                className="h-20 flex flex-col items-center gap-2"
                onClick={() => alert('Monitoring functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-green" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>
                </svg>
                <span className="text-redis-xs">Monitoring</span>
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
                onClick={() => alert('Incidents functionality would go here')}
              >
                <svg className="h-6 w-6 text-redis-red" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M13,14H11V10H13M13,18H11V16H13M1,21H23L12,2L1,21Z"/>
                </svg>
                <span className="text-redis-xs">Incidents</span>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Dashboard;
