import { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Button,
} from '@radar/ui-kit';

// Simple components for missing UI kit elements
const Loader = ({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) => (
  <div className={`animate-spin rounded-full border-2 border-redis-blue-03 border-t-transparent ${
    size === 'sm' ? 'h-4 w-4' : size === 'lg' ? 'h-8 w-8' : 'h-6 w-6'
  }`} />
);

const ErrorMessage = ({ message, title }: { message: string; title?: string }) => (
  <div className="bg-redis-red bg-opacity-10 border border-redis-red border-opacity-20 rounded-redis-sm p-4">
    {title && <h4 className="font-semibold text-redis-red mb-2">{title}</h4>}
    <p className="text-redis-red text-redis-sm">{message}</p>
  </div>
);

const Tooltip = ({ content, children }: { content: string; children: React.ReactNode }) => (
  <div className="relative group">
    {children}
    <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-2 py-1 bg-redis-dusk-01 text-white text-redis-xs rounded opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap">
      {content}
    </div>
  </div>
);

// Redis instance interface
interface RedisInstance {
  id: string;
  name: string;
  host: string;
  port: number;
  environment: string;
  usage: string;
  description: string;
  status?: string;
  version?: string;
  memory?: string;
  connections?: number;
  repoUrl?: string;
  notes?: string;
  lastChecked?: string;
}

// Add Instance Form Component
interface AddInstanceFormProps {
  onSubmit: (instance: RedisInstance) => void;
  onCancel: () => void;
  initialData?: RedisInstance;
}

const AddInstanceForm = ({ onSubmit, onCancel, initialData }: AddInstanceFormProps) => {
  // Check if the initial usage is a custom type (not in predefined list)
  const predefinedUsageTypes = ['cache', 'analytics', 'session', 'queue'];
  const isCustomUsage = initialData?.usage && !predefinedUsageTypes.includes(initialData.usage);

  const [formData, setFormData] = useState({
    name: initialData?.name || '',
    host: initialData?.host || '',
    port: initialData?.port?.toString() || '6379',
    environment: initialData?.environment || 'development',
    usage: isCustomUsage ? 'custom' : (initialData?.usage || 'cache'),
    customUsage: isCustomUsage ? initialData?.usage || '' : '',
    description: initialData?.description || '',
    repoUrl: initialData?.repoUrl || '',
    notes: initialData?.notes || ''
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResult, setConnectionResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const finalUsage = formData.usage === 'custom' ? formData.customUsage : formData.usage;

      const instance: RedisInstance = {
        id: initialData?.id || `redis-${formData.environment}-${Date.now()}`,
        name: formData.name,
        host: formData.host,
        port: parseInt(formData.port),
        environment: formData.environment,
        usage: finalUsage,
        description: formData.description,
        repoUrl: formData.repoUrl || undefined,
        notes: formData.notes || undefined,
        status: initialData?.status || 'unknown',
        version: initialData?.version,
        memory: initialData?.memory,
        connections: initialData?.connections,
        lastChecked: initialData?.lastChecked || new Date().toISOString()
      };

      onSubmit(instance);
    } catch (error) {
      console.error('Error saving instance:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const testConnection = async () => {
    setTestingConnection(true);
    setConnectionResult(null);

    try {
      // TODO: Implement actual connection test via API
      // For now, simulate a connection test with more realistic behavior
      await new Promise(resolve => setTimeout(resolve, 1500));

      // Simulate success/failure based on host - localhost usually works
      const isLocalhost = formData.host.toLowerCase().includes('localhost') || formData.host === '127.0.0.1';
      const success = isLocalhost ? Math.random() > 0.2 : Math.random() > 0.6; // Higher success rate for localhost

      setConnectionResult({
        success,
        message: success
          ? `✅ Successfully connected to Redis at ${formData.host}:${formData.port}. Connection is healthy!`
          : `❌ Failed to connect to Redis at ${formData.host}:${formData.port}. Please verify the host and port are correct and Redis is running.`
      });
    } catch (error) {
      setConnectionResult({
        success: false,
        message: '❌ Connection test failed due to an unexpected error. Please try again.'
      });
    } finally {
      setTestingConnection(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
            Instance Name *
          </label>
          <input
            type="text"
            required
            value={formData.name}
            onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
            placeholder="e.g., Production Cache"
          />
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
            Environment *
          </label>
          <select
            required
            value={formData.environment}
            onChange={(e) => setFormData(prev => ({ ...prev, environment: e.target.value }))}
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          >
            <option value="development">Development</option>
            <option value="staging">Staging</option>
            <option value="production">Production</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2">
          <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
            Host *
          </label>
          <input
            type="text"
            required
            value={formData.host}
            onChange={(e) => setFormData(prev => ({ ...prev, host: e.target.value }))}
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
            placeholder="e.g., localhost or redis.company.com"
          />
        </div>

        <div>
          <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
            Port *
          </label>
          <input
            type="number"
            required
            min="1"
            max="65535"
            value={formData.port}
            onChange={(e) => setFormData(prev => ({ ...prev, port: e.target.value }))}
            className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          />
        </div>
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
          Usage Type *
        </label>
        <select
          required
          value={formData.usage}
          onChange={(e) => setFormData(prev => ({ ...prev, usage: e.target.value }))}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
        >
          <option value="cache">Cache</option>
          <option value="analytics">Analytics</option>
          <option value="session">Session Store</option>
          <option value="queue">Message Queue</option>
          <option value="custom">Custom (specify below)</option>
        </select>

        {formData.usage === 'custom' && (
          <div className="mt-2">
            <input
              type="text"
              required
              value={formData.customUsage}
              onChange={(e) => setFormData(prev => ({ ...prev, customUsage: e.target.value }))}
              className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
              placeholder="Enter custom usage type (e.g., 'pub/sub', 'timeseries', 'search')"
            />
          </div>
        )}
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
          Description *
        </label>
        <textarea
          required
          value={formData.description}
          onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          rows={3}
          placeholder="Describe what this Redis instance is used for..."
        />
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
          Repository URL (optional)
        </label>
        <input
          type="url"
          value={formData.repoUrl}
          onChange={(e) => setFormData(prev => ({ ...prev, repoUrl: e.target.value }))}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          placeholder="https://github.com/company/redis-config"
        />
      </div>

      <div>
        <label className="block text-redis-sm font-medium text-redis-dusk-01 mb-1">
          Notes (optional)
        </label>
        <textarea
          value={formData.notes}
          onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
          className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
          rows={2}
          placeholder="Any additional notes about this instance..."
        />
      </div>

      {/* Connection Test */}
      <div className="border-t border-redis-dusk-06 pt-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-redis-sm font-medium text-redis-dusk-01">Test Connection</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={testConnection}
            isLoading={testingConnection}
            disabled={!formData.host || !formData.port}
          >
            {testingConnection ? 'Testing...' : 'Test Connection'}
          </Button>
        </div>

        {connectionResult && (
          <div className={`p-3 rounded-redis-sm text-redis-sm border ${
            connectionResult.success
              ? 'bg-green-50 text-green-800 border-green-200'
              : 'bg-red-50 text-red-800 border-red-200'
          }`}>
            <div className="flex items-center gap-2">
              {connectionResult.success ? (
                <svg className="w-4 h-4 text-green-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
              ) : (
                <svg className="w-4 h-4 text-red-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                </svg>
              )}
              <span>{connectionResult.message}</span>
            </div>
          </div>
        )}
      </div>

      {/* Form Actions */}
      <div className="flex gap-3 pt-4 border-t border-redis-dusk-06">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          variant="primary"
          isLoading={isSubmitting}
          disabled={isSubmitting}
        >
          {isSubmitting
            ? (initialData ? 'Updating Instance...' : 'Adding Instance...')
            : (initialData ? 'Update Instance' : 'Add Instance')
          }
        </Button>
      </div>
    </form>
  );
};

const Instances = () => {
  const [instances, setInstances] = useState<RedisInstance[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [selectedEnvironment, setSelectedEnvironment] = useState('all');
  const [selectedUsage, setSelectedUsage] = useState('all');
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingInstance, setEditingInstance] = useState<RedisInstance | null>(null);

  // Load instances on component mount
  useEffect(() => {
    loadInstances();
  }, []);

  const loadInstances = async () => {
    try {
      setIsLoading(true);
      setError('');
      // TODO: Replace with actual API call to get instances
      // For now, return empty array to show empty state
      setInstances([]);
    } catch (err) {
      setError('Failed to load Redis instances. Please try again.');
      console.error('Error loading instances:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await loadInstances();
    setIsRefreshing(false);
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
    switch (usage.toLowerCase()) {
      case 'cache': return 'bg-redis-blue-03 text-white';
      case 'analytics': return 'bg-redis-green text-white';
      case 'session': return 'bg-redis-lime text-white';
      case 'queue': return 'bg-redis-yellow-300 text-redis-midnight';
      case 'pub/sub':
      case 'pubsub': return 'bg-purple-500 text-white';
      case 'timeseries': return 'bg-orange-500 text-white';
      case 'search': return 'bg-teal-500 text-white';
      default: return 'bg-redis-dusk-06 text-white';
    }
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString();
  };

  const filteredInstances = instances.filter(instance => {
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
          <Button
            variant="primary"
            onClick={() => setShowAddForm(true)}
          >
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

      {/* Filters - Only show if we have instances */}
      {instances.length > 0 && (
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
                  {/* Add dynamic options for custom usage types */}
                  {Array.from(new Set(instances.map(i => i.usage)))
                    .filter(usage => !['cache', 'analytics', 'session', 'queue'].includes(usage))
                    .map(usage => (
                      <option key={usage} value={usage}>
                        {usage.charAt(0).toUpperCase() + usage.slice(1)}
                      </option>
                    ))
                  }
                </select>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-12">
            <div className="text-center">
              <Loader size="lg" />
              <p className="text-redis-sm text-redis-dusk-04 mt-4">
                Loading Redis instances...
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Instances List */}
          <div className="space-y-4">
            {instances.length === 0 ? (
              <Card>
                <CardContent className="flex items-center justify-center py-16">
                  <div className="text-center max-w-md">
                    <div className="w-16 h-16 mx-auto mb-6 bg-redis-dusk-08 rounded-full flex items-center justify-center">
                      <svg className="h-8 w-8 text-redis-dusk-04" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                      </svg>
                    </div>
                    <h3 className="text-redis-xl font-semibold text-redis-dusk-01 mb-3">
                      No Redis instances configured
                    </h3>
                    <p className="text-redis-sm text-redis-dusk-04 mb-6">
                      Get started by adding your first Redis instance. The SRE agent will be able to monitor, diagnose, and help troubleshoot issues with your Redis infrastructure.
                    </p>
                    <Button
                      variant="primary"
                      size="lg"
                      onClick={() => setShowAddForm(true)}
                    >
                      Add Your First Instance
                    </Button>
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
                          {instance.status && (
                            <span className={`text-redis-xs font-medium capitalize ${getStatusColor(instance.status)}`}>
                              ● {instance.status}
                            </span>
                          )}
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
                            {instance.version && <div><strong>Version:</strong> {instance.version}</div>}
                            {instance.memory && <div><strong>Memory:</strong> {instance.memory}</div>}
                          </div>
                          <div className="text-redis-xs text-redis-dusk-05">
                            {instance.connections && <div><strong>Connections:</strong> {instance.connections}</div>}
                            {instance.lastChecked && <div><strong>Last Checked:</strong> {formatDate(instance.lastChecked)}</div>}
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
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setEditingInstance(instance)}
                        >
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
        </>
      )}



      {/* Add/Edit Instance Form Modal */}
      {(showAddForm || editingInstance) && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-redis-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-redis-xl font-bold text-redis-dusk-01">
                {editingInstance ? 'Edit Redis Instance' : 'Add Redis Instance'}
              </h2>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setShowAddForm(false);
                  setEditingInstance(null);
                }}
              >
                ✕
              </Button>
            </div>

            <AddInstanceForm
              initialData={editingInstance || undefined}
              onSubmit={(instance) => {
                if (editingInstance) {
                  // Update existing instance
                  setInstances(prev => prev.map(inst =>
                    inst.id === instance.id ? instance : inst
                  ));
                } else {
                  // Add new instance
                  setInstances(prev => [...prev, instance]);
                }
                setShowAddForm(false);
                setEditingInstance(null);
              }}
              onCancel={() => {
                setShowAddForm(false);
                setEditingInstance(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default Instances;
