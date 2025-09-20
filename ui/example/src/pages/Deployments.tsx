import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  CollapsibleCard,
  Tooltip,
  ErrorMessage,
  Avatar,
  DropdownMenu,
  Loader,
  type CollapsibleSection,
  type DropdownMenuItem
} from '@radar/ui-kit';

// Mock deployment data
const mockDeployments = [
  {
    id: 'deploy_prod_001',
    name: 'Production Redis Cluster',
    type: 'enterprise',
    status: 'healthy',
    environment: 'production',
    region: 'us-east-1',
    host: 'redis-prod.example.com',
    port: 6379,
    databases: 12,
    memory: {
      used: '4.2GB',
      total: '8GB',
      percentage: 52
    },
    cpu: {
      usage: 23,
      cores: 4
    },
    connections: {
      active: 847,
      max: 1000
    },
    uptime: '99.98%',
    lastBackup: '2024-03-15T06:00:00Z',
    version: '7.2.4',
    ssl: true,
    auth: true,
    monitoring: {
      alerts: 0,
      warnings: 1,
      lastCheck: '2024-03-15T14:30:00Z'
    }
  },
  {
    id: 'deploy_stage_002',
    name: 'Staging Environment',
    type: 'standalone',
    status: 'warning',
    environment: 'staging',
    region: 'us-west-2',
    host: 'redis-staging.example.com',
    port: 6379,
    databases: 5,
    memory: {
      used: '1.8GB',
      total: '4GB',
      percentage: 45
    },
    cpu: {
      usage: 67,
      cores: 2
    },
    connections: {
      active: 234,
      max: 500
    },
    uptime: '99.12%',
    lastBackup: '2024-03-15T02:00:00Z',
    version: '7.2.4',
    ssl: false,
    auth: true,
    monitoring: {
      alerts: 0,
      warnings: 3,
      lastCheck: '2024-03-15T14:29:00Z'
    }
  },
  {
    id: 'deploy_dev_003',
    name: 'Development Instance',
    type: 'standalone',
    status: 'critical',
    environment: 'development',
    region: 'us-east-1',
    host: 'redis-dev.example.com',
    port: 6379,
    databases: 3,
    memory: {
      used: '950MB',
      total: '2GB',
      percentage: 47
    },
    cpu: {
      usage: 89,
      cores: 1
    },
    connections: {
      active: 45,
      max: 100
    },
    uptime: '94.23%',
    lastBackup: '2024-03-14T18:00:00Z',
    version: '7.0.15',
    ssl: false,
    auth: false,
    monitoring: {
      alerts: 2,
      warnings: 1,
      lastCheck: '2024-03-15T14:28:00Z'
    }
  }
];

const performanceMetrics = [
  { name: 'Throughput', value: '15.2K', unit: 'ops/sec', trend: '+5.2%', positive: true },
  { name: 'Latency', value: '0.84', unit: 'ms avg', trend: '-12%', positive: true },
  { name: 'Hit Rate', value: '94.7', unit: '%', trend: '+0.3%', positive: true },
  { name: 'Memory Efficiency', value: '87.2', unit: '%', trend: '+1.1%', positive: true }
];

const alerts = [
  {
    id: 'alert_001',
    severity: 'critical',
    deployment: 'Development Instance',
    message: 'CPU usage consistently above 85% for 15 minutes',
    timestamp: '2024-03-15T14:15:00Z',
    acknowledged: false
  },
  {
    id: 'alert_002',
    severity: 'warning',
    deployment: 'Staging Environment',
    message: 'Connection pool utilization above 70%',
    timestamp: '2024-03-15T13:45:00Z',
    acknowledged: false
  },
  {
    id: 'alert_003',
    severity: 'critical',
    deployment: 'Development Instance',
    message: 'Memory usage approaching limit (95%)',
    timestamp: '2024-03-15T13:30:00Z',
    acknowledged: true
  }
];

const Deployments = () => {
  const [deployments] = useState(mockDeployments);
  const [selectedDeployment, setSelectedDeployment] = useState(mockDeployments[0]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const filteredDeployments = deployments.filter(deployment =>
    deployment.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    deployment.environment.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await new Promise(resolve => setTimeout(resolve, 2000));
    setIsRefreshing(false);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return 'text-redis-green bg-redis-green/20';
      case 'warning': return 'text-redis-yellow-500 bg-redis-yellow-500/20';
      case 'critical': return 'text-redis-red bg-redis-red/20';
      default: return 'text-redis-dusk-04 bg-redis-dusk-07';
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return 'text-redis-red bg-redis-red/20 border-redis-red/30';
      case 'warning': return 'text-redis-yellow-500 bg-redis-yellow-500/20 border-redis-yellow-500/30';
      case 'info': return 'text-redis-blue-03 bg-redis-blue-03/20 border-redis-blue-03/30';
      default: return 'text-redis-dusk-04 bg-redis-dusk-07 border-redis-dusk-08';
    }
  };

  const getDeploymentActions = (deployment: any): DropdownMenuItem[] => [
    {
      label: 'View Details',
      onClick: () => alert(`Viewing details for ${deployment.name}`)
    },
    {
      label: 'Edit Configuration',
      onClick: () => alert(`Editing ${deployment.name}`)
    },
    {
      label: 'View Logs',
      onClick: () => alert(`Opening logs for ${deployment.name}`)
    },
    {
      label: 'Create Backup',
      onClick: () => alert(`Creating backup for ${deployment.name}`)
    },
    {
      label: 'Restart Instance',
      onClick: () => {
        if (confirm(`Are you sure you want to restart ${deployment.name}?`)) {
          alert(`${deployment.name} would be restarted`);
        }
      },
      variant: 'destructive'
    }
  ];

  const overviewSection: CollapsibleSection = {
    id: 'overview',
    title: 'Deployment Overview',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {performanceMetrics.map((metric, index) => (
            <div key={index} className="p-4 bg-redis-dusk-09 rounded-redis-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="text-redis-xs text-redis-dusk-04 font-medium">{metric.name}</span>
                <span className={`text-redis-xs font-medium ${
                  metric.positive ? 'text-redis-green' : 'text-redis-red'
                }`}>
                  {metric.trend}
                </span>
              </div>
              <div className="flex items-end gap-1">
                <span className="text-redis-lg font-bold text-redis-dusk-01">{metric.value}</span>
                <span className="text-redis-xs text-redis-dusk-04">{metric.unit}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div>
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Resource Usage</h4>
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-redis-sm text-redis-dusk-01">Memory</span>
                  <span className="text-redis-sm text-redis-dusk-04">
                    {selectedDeployment.memory.used} / {selectedDeployment.memory.total}
                  </span>
                </div>
                <div className="w-full bg-redis-dusk-08 rounded-redis-sm h-2">
                  <div
                    className="h-2 bg-redis-blue-03 rounded-redis-sm transition-all"
                    style={{ width: `${selectedDeployment.memory.percentage}%` }}
                  />
                </div>
                <span className="text-redis-xs text-redis-dusk-04 mt-1">
                  {selectedDeployment.memory.percentage}% used
                </span>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-redis-sm text-redis-dusk-01">CPU</span>
                  <span className="text-redis-sm text-redis-dusk-04">
                    {selectedDeployment.cpu.cores} cores
                  </span>
                </div>
                <div className="w-full bg-redis-dusk-08 rounded-redis-sm h-2">
                  <div
                    className={`h-2 rounded-redis-sm transition-all ${
                      selectedDeployment.cpu.usage > 80 ? 'bg-redis-red' :
                      selectedDeployment.cpu.usage > 60 ? 'bg-redis-yellow-500' :
                      'bg-redis-green'
                    }`}
                    style={{ width: `${selectedDeployment.cpu.usage}%` }}
                  />
                </div>
                <span className="text-redis-xs text-redis-dusk-04 mt-1">
                  {selectedDeployment.cpu.usage}% usage
                </span>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-redis-sm text-redis-dusk-01">Connections</span>
                  <span className="text-redis-sm text-redis-dusk-04">
                    {selectedDeployment.connections.active} / {selectedDeployment.connections.max}
                  </span>
                </div>
                <div className="w-full bg-redis-dusk-08 rounded-redis-sm h-2">
                  <div
                    className="h-2 bg-redis-blue-03 rounded-redis-sm transition-all"
                    style={{ width: `${(selectedDeployment.connections.active / selectedDeployment.connections.max) * 100}%` }}
                  />
                </div>
                <span className="text-redis-xs text-redis-dusk-04 mt-1">
                  {Math.round((selectedDeployment.connections.active / selectedDeployment.connections.max) * 100)}% capacity
                </span>
              </div>
            </div>
          </div>

          <div>
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Configuration</h4>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                <span className="text-redis-sm text-redis-dusk-04">Host</span>
                <code className="text-redis-sm text-redis-dusk-01 font-mono">{selectedDeployment.host}</code>
              </div>
              <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                <span className="text-redis-sm text-redis-dusk-04">Port</span>
                <code className="text-redis-sm text-redis-dusk-01 font-mono">{selectedDeployment.port}</code>
              </div>
              <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                <span className="text-redis-sm text-redis-dusk-04">Version</span>
                <code className="text-redis-sm text-redis-dusk-01 font-mono">{selectedDeployment.version}</code>
              </div>
              <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                <span className="text-redis-sm text-redis-dusk-04">SSL/TLS</span>
                <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                  selectedDeployment.ssl
                    ? 'text-redis-green bg-redis-green/20'
                    : 'text-redis-red bg-redis-red/20'
                }`}>
                  {selectedDeployment.ssl ? 'Enabled' : 'Disabled'}
                </span>
              </div>
              <div className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                <span className="text-redis-sm text-redis-dusk-04">Authentication</span>
                <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                  selectedDeployment.auth
                    ? 'text-redis-green bg-redis-green/20'
                    : 'text-redis-red bg-redis-red/20'
                }`}>
                  {selectedDeployment.auth ? 'Required' : 'Disabled'}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  };

  const alertsSection: CollapsibleSection = {
    id: 'alerts',
    title: 'Monitoring & Alerts',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div>
          <div className="flex items-center justify-between mb-4">
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01">Recent Alerts</h4>
            <div className="flex gap-2">
              <Button variant="outline" size="sm">Mark All Read</Button>
              <Button variant="outline" size="sm">Configure Rules</Button>
            </div>
          </div>

          <div className="space-y-3">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className={`p-4 rounded-redis-sm border ${getSeverityColor(alert.severity)} ${
                  alert.acknowledged ? 'opacity-60' : ''
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getSeverityColor(alert.severity)}`}>
                        {alert.severity.toUpperCase()}
                      </span>
                      <span className="text-redis-sm font-medium text-redis-dusk-01">
                        {alert.deployment}
                      </span>
                      <span className="text-redis-xs text-redis-dusk-04">
                        {new Date(alert.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-redis-sm text-redis-dusk-04">{alert.message}</p>
                  </div>
                  <div className="flex gap-2 ml-4">
                    {!alert.acknowledged && (
                      <Button variant="outline" size="sm">
                        Acknowledge
                      </Button>
                    )}
                    <Button variant="ghost" size="sm">
                      View Details
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="pt-6 border-t border-redis-dusk-08">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Alert Rules</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { name: 'High CPU Usage', threshold: '> 80% for 10 min', enabled: true },
              { name: 'Memory Usage', threshold: '> 90% for 5 min', enabled: true },
              { name: 'Connection Limit', threshold: '> 95% capacity', enabled: true },
              { name: 'Response Time', threshold: '> 100ms avg', enabled: false }
            ].map((rule, index) => (
              <div key={index} className="flex items-center justify-between p-3 border border-redis-dusk-08 rounded-redis-sm">
                <div>
                  <p className="text-redis-sm font-medium text-redis-dusk-01">{rule.name}</p>
                  <p className="text-redis-xs text-redis-dusk-04">{rule.threshold}</p>
                </div>
                <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                  rule.enabled
                    ? 'text-redis-green bg-redis-green/20'
                    : 'text-redis-dusk-04 bg-redis-dusk-07'
                }`}>
                  {rule.enabled ? 'Active' : 'Disabled'}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Deployments</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Monitor and manage your Redis deployments across all environments
          </p>
        </div>
        <div className="flex gap-2">
          <Tooltip content="Refresh all deployment data">
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

      {/* Search and Filters */}
      <Card>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <Input
                placeholder="Search deployments by name or environment..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </div>
            <Button variant="outline">Filter by Status</Button>
            <Button variant="outline">Filter by Region</Button>
          </div>
        </CardContent>
      </Card>

      {/* Deployments Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Deployment List */}
        <div className="lg:col-span-1">
          <Card>
            <CardHeader>
              <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
                Deployments ({filteredDeployments.length})
              </h3>
            </CardHeader>
            <CardContent className="p-0">
              <div className="divide-y divide-redis-dusk-08">
                {filteredDeployments.map((deployment) => (
                  <button
                    key={deployment.id}
                    onClick={() => setSelectedDeployment(deployment)}
                    className={`w-full text-left p-3 m-2 rounded-redis-sm hover:bg-redis-dusk-09 transition-colors ${
                      selectedDeployment.id === deployment.id ? 'bg-redis-dusk-09' : ''
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <h4 className="text-redis-sm font-medium text-redis-dusk-01">{deployment.name}</h4>
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getStatusColor(deployment.status)}`}>
                        {deployment.status}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-redis-xs text-redis-dusk-04">
                      <span>{deployment.environment}</span>
                      <span>{deployment.region}</span>
                      <span>{deployment.type}</span>
                    </div>
                    <div className="flex items-center justify-end mt-1">
                      <DropdownMenu
                        trigger={
                          <Button variant="ghost" size="sm" onClick={(e) => e.stopPropagation()}>
                            <span className="text-redis-dusk-04">⋯</span>
                          </Button>
                        }
                        items={getDeploymentActions(deployment)}
                        placement="bottom-right"
                      />
                    </div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Deployment Details */}
        <div className="lg:col-span-2">
          <div className="space-y-6">
            {/* Header */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-redis-lg font-semibold text-redis-dusk-01">{selectedDeployment.name}</h3>
                    <div className="flex items-center gap-2 mt-1">
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getStatusColor(selectedDeployment.status)}`}>
                        {selectedDeployment.status}
                      </span>
                      <span className="text-redis-xs text-redis-dusk-04">{selectedDeployment.environment}</span>
                      <span className="text-redis-xs text-redis-dusk-04">•</span>
                      <span className="text-redis-xs text-redis-dusk-04">{selectedDeployment.region}</span>
                      <span className="text-redis-xs text-redis-dusk-04">•</span>
                      <span className="text-redis-xs text-redis-dusk-04">Uptime: {selectedDeployment.uptime}</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm">View Logs</Button>
                    <Button variant="outline" size="sm">Edit Config</Button>
                  </div>
                </div>
              </CardHeader>
            </Card>

            {/* Detailed Sections */}
            <CollapsibleCard
              title="Deployment Details"
              description="Comprehensive monitoring and configuration for your Redis deployment"
              sections={[overviewSection, alertsSection]}
              defaultExpandedSection="overview"
              allowMultipleExpanded={true}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Deployments;
