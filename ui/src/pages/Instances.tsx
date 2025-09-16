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

// Mock data for Redis instances
const redisInstances = [
  {
    id: 'redis-prod-01',
    name: 'Production Cache',
    host: 'redis-prod-01.company.com',
    port: 6379,
    environment: 'production',
    usage: 'cache',
    description: 'Primary cache for user sessions and application data',
    status: 'healthy',
    version: '7.2.4',
    memory: '8GB',
    connections: 245,
    repoUrl: 'https://github.com/company/redis-config',
    notes: 'Critical instance - handles all user session data',
    lastChecked: '2024-01-15T12:30:00Z'
  },
  {
    id: 'redis-analytics-01',
    name: 'Analytics Store',
    host: 'redis-analytics-01.company.com',
    port: 6379,
    environment: 'production',
    usage: 'analytics',
    description: 'Time-series data storage for analytics and metrics',
    status: 'healthy',
    version: '7.2.4',
    memory: '16GB',
    connections: 89,
    repoUrl: 'https://github.com/company/analytics-redis',
    notes: 'Uses Redis Streams for real-time analytics pipeline',
    lastChecked: '2024-01-15T12:28:00Z'
  },
  {
    id: 'redis-staging-01',
    name: 'Staging Environment',
    host: 'redis-staging-01.company.com',
    port: 6379,
    environment: 'staging',
    usage: 'cache',
    description: 'Staging environment for testing and development',
    status: 'warning',
    version: '7.0.15',
    memory: '4GB',
    connections: 12,
    repoUrl: 'https://github.com/company/redis-config',
    notes: 'Needs version upgrade to match production',
    lastChecked: '2024-01-15T12:25:00Z'
  }
];

const Instances = () => {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [selectedEnvironment, setSelectedEnvironment] = useState('all');
  const [selectedUsage, setSelectedUsage] = useState('all');

  const handleRefresh = async () => {
    setIsRefreshing(true);
    setError('');

    // Simulate API call
    setTimeout(() => {
      if (Math.random() > 0.8) {
        setError('Failed to refresh Redis instances data. Please try again.');
      }
      setIsRefreshing(false);
    }, 2000);
  };

  const getEnvironmentColor = (environment: string) => {
    switch (environment) {
      case 'production': return 'bg-redis-red text-white';
      case 'staging': return 'bg-redis-yellow-500 text-redis-midnight';
      case 'development': return 'bg-redis-blue-03 text-white';
      default: return 'bg-redis-dusk-06 text-white';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-redis-green';
      case 'warning': return 'text-redis-yellow-500';
      case 'critical': return 'text-redis-red';
      case 'offline': return 'text-redis-dusk-04';
      default: return 'text-redis-dusk-04';
    }
  };

  const getUsageColor = (usage: string) => {
    switch (usage) {
      case 'cache': return 'bg-redis-blue-03 text-white';
      case 'analytics': return 'bg-redis-green text-white';
      case 'session': return 'bg-redis-lime text-white';
      case 'queue': return 'bg-redis-yellow-300 text-redis-midnight';
      default: return 'bg-redis-dusk-06 text-white';
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const filteredInstances = redisInstances.filter(instance => {
    const environmentMatch = selectedEnvironment === 'all' || instance.environment === selectedEnvironment;
    const usageMatch = selectedUsage === 'all' || instance.usage === selectedUsage;
    return environmentMatch && usageMatch;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Redis Instances</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Manage and monitor Redis instances that the SRE agent can triage and analyze.
          </p>
        </div>
        <div className="flex gap-2">
          <Tooltip content="Refresh instances data">
            <Button
              variant="outline"
              onClick={handleRefresh}
              isLoading={isRefreshing}
            >
              {isRefreshing ? <Loader size="sm" /> : 'Refresh'}
            </Button>
          </Tooltip>
          <Button variant="primary">
            Add Instance
          </Button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <ErrorMessage
          message={error}
          title="Redis Instances Error"
        />
      )}

      {/* Filters */}
      <Card>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-redis-sm text-redis-dusk-04">Environment:</label>
              <select
                value={selectedEnvironment}
                onChange={(e) => setSelectedEnvironment(e.target.value)}
                className="px-3 py-1 border border-redis-dusk-06 rounded-redis-sm text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
              >
                <option value="all">All</option>
                <option value="production">Production</option>
                <option value="staging">Staging</option>
                <option value="development">Development</option>
              </select>
            </div>
            <div className="flex items-center gap-2">
              <label className="text-redis-sm text-redis-dusk-04">Usage:</label>
              <select
                value={selectedUsage}
                onChange={(e) => setSelectedUsage(e.target.value)}
                className="px-3 py-1 border border-redis-dusk-06 rounded-redis-sm text-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
              >
                <option value="all">All</option>
                <option value="cache">Cache</option>
                <option value="analytics">Analytics</option>
                <option value="session">Session Store</option>
                <option value="queue">Message Queue</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Instances List */}
      <div className="space-y-4">
        {filteredInstances.length === 0 ? (
          <Card>
            <CardContent className="flex items-center justify-center py-12">
              <div className="text-center">
                <svg className="h-12 w-12 text-redis-dusk-04 mx-auto mb-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12,6A6,6 0 0,0 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12A6,6 0 0,0 12,6Z"/>
                </svg>
                <h3 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
                  No Redis instances found
                </h3>
                <p className="text-redis-sm text-redis-dusk-04">
                  No Redis instances match your current filters.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          filteredInstances.map((instance) => (
            <Card key={instance.id} className="hover:shadow-lg transition-shadow">
              <CardContent>
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <span className="text-redis-sm font-mono text-redis-dusk-04">
                        {instance.id}
                      </span>
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getEnvironmentColor(instance.environment)}`}>
                        {instance.environment.toUpperCase()}
                      </span>
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getUsageColor(instance.usage)}`}>
                        {instance.usage.toUpperCase()}
                      </span>
                      <span className={`text-redis-xs font-medium capitalize ${getStatusColor(instance.status)}`}>
                        ● {instance.status}
                      </span>
                    </div>
                    <h3 className="text-redis-lg font-semibold text-redis-dusk-01 mb-2">
                      {instance.name}
                    </h3>
                    <p className="text-redis-sm text-redis-dusk-04 mb-3">
                      {instance.description}
                    </p>
                    <div className="grid grid-cols-2 gap-4 mb-3">
                      <div className="text-redis-xs text-redis-dusk-05">
                        <div><strong>Host:</strong> {instance.host}:{instance.port}</div>
                        <div><strong>Version:</strong> {instance.version}</div>
                        <div><strong>Memory:</strong> {instance.memory}</div>
                      </div>
                      <div className="text-redis-xs text-redis-dusk-05">
                        <div><strong>Connections:</strong> {instance.connections}</div>
                        <div><strong>Last Checked:</strong> {formatDate(instance.lastChecked)}</div>
                      </div>
                    </div>
                    {instance.repoUrl && (
                      <div className="mb-2">
                        <span className="text-redis-xs text-redis-dusk-04">Repository: </span>
                        <a href={instance.repoUrl} target="_blank" rel="noopener noreferrer"
                           className="text-redis-xs text-redis-blue-03 hover:underline">
                          {instance.repoUrl}
                        </a>
                      </div>
                    )}
                    {instance.notes && (
                      <div className="mt-2 p-2 bg-redis-dusk-09 rounded-redis-sm">
                        <span className="text-redis-xs text-redis-dusk-04">Notes: </span>
                        <span className="text-redis-xs text-redis-dusk-01">{instance.notes}</span>
                      </div>
                    )}
                  </div>
                  <div className="flex gap-2 ml-4">
                    <Button variant="outline" size="sm">
                      Edit
                    </Button>
                    <Button variant="primary" size="sm">
                      Test Connection
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent>
            <div className="text-center">
              <p className="text-redis-xl font-bold text-redis-green">{filteredInstances.filter(i => i.status === 'healthy').length}</p>
              <p className="text-redis-xs text-redis-dusk-04">Healthy Instances</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-center">
              <p className="text-redis-xl font-bold text-redis-yellow-500">{filteredInstances.filter(i => i.status === 'warning').length}</p>
              <p className="text-redis-xs text-redis-dusk-04">Warning Status</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-center">
              <p className="text-redis-xl font-bold text-redis-red">{filteredInstances.filter(i => i.environment === 'production').length}</p>
              <p className="text-redis-xs text-redis-dusk-04">Production Instances</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <div className="text-center">
              <p className="text-redis-xl font-bold text-redis-blue-03">{filteredInstances.reduce((sum, i) => sum + i.connections, 0)}</p>
              <p className="text-redis-xs text-redis-dusk-04">Total Connections</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Instances;
