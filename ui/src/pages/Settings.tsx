import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Loader,
  ErrorMessage,
} from '@radar/ui-kit';
import Instances from './Instances';

interface KnowledgeSettings {
  chunk_size: number;
  chunk_overlap: number;
  splitting_strategy: string;
  embedding_model: string;
  max_documents_per_batch: number;
  enable_metadata_extraction: boolean;
  enable_semantic_chunking: boolean;
  similarity_threshold: number;
  created_at: string;
  updated_at: string;
}

const KnowledgeSettingsSection = () => {
  const [settings, setSettings] = useState<KnowledgeSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [pendingSettings, setPendingSettings] = useState<Partial<KnowledgeSettings> | null>(null);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setError(null);
      const response = await fetch('/api/v1/knowledge/settings');
      if (!response.ok) {
        throw new Error('Failed to load knowledge settings');
      }
      const data = await response.json();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async (newSettings: Partial<KnowledgeSettings>) => {
    setPendingSettings(newSettings);
    setShowConfirmDialog(true);
  };

  const confirmSave = async () => {
    if (!pendingSettings) return;

    try {
      setIsSaving(true);
      setError(null);

      const response = await fetch('/api/v1/knowledge/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pendingSettings),
      });

      if (!response.ok) {
        throw new Error('Failed to update settings');
      }

      const updatedSettings = await response.json();
      setSettings(updatedSettings);
      setShowConfirmDialog(false);
      setPendingSettings(null);

      // Note: In a real implementation, this would trigger a re-ingestion job
      alert('Settings updated successfully! A new ingestion job will be started to apply these changes.');

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update settings');
    } finally {
      setIsSaving(false);
    }
  };

  const resetToDefaults = async () => {
    try {
      setIsSaving(true);
      setError(null);

      const response = await fetch('/api/v1/knowledge/settings/reset', {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('Failed to reset settings');
      }

      const defaultSettings = await response.json();
      setSettings(defaultSettings);

    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset settings');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader size="lg" />
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="text-center py-8">
        <p className="text-redis-dusk-04">Failed to load knowledge settings</p>
        <Button variant="outline" onClick={loadSettings} className="mt-4">
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <ErrorMessage
          message={error}
          title="Settings Error"
        />
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-redis-lg font-semibold text-foreground">Ingestion Settings</h3>
            <Button variant="outline" onClick={resetToDefaults} disabled={isSaving}>
              Reset to Defaults
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={(e) => {
            e.preventDefault();
            const formData = new FormData(e.currentTarget);
            const newSettings = {
              chunk_size: parseInt(formData.get('chunk_size') as string),
              chunk_overlap: parseInt(formData.get('chunk_overlap') as string),
              splitting_strategy: formData.get('splitting_strategy') as string,
              embedding_model: formData.get('embedding_model') as string,
              max_documents_per_batch: parseInt(formData.get('max_documents_per_batch') as string),
              enable_metadata_extraction: formData.get('enable_metadata_extraction') === 'on',
              enable_semantic_chunking: formData.get('enable_semantic_chunking') === 'on',
              similarity_threshold: parseFloat(formData.get('similarity_threshold') as string),
            };
            handleSave(newSettings);
          }}>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Chunk Size
                </label>
                <input
                  type="number"
                  name="chunk_size"
                  min="100"
                  max="4000"
                  defaultValue={settings.chunk_size}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                />
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Size of text chunks for processing (100-4000 characters)
                </p>
              </div>

              <div>
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Chunk Overlap
                </label>
                <input
                  type="number"
                  name="chunk_overlap"
                  min="0"
                  max="1000"
                  defaultValue={settings.chunk_overlap}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                />
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Overlap between consecutive chunks (0-1000 characters)
                </p>
              </div>

              <div>
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Splitting Strategy
                </label>
                <select
                  name="splitting_strategy"
                  defaultValue={settings.splitting_strategy}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                >
                  <option value="recursive">Recursive</option>
                  <option value="semantic">Semantic</option>
                  <option value="fixed">Fixed</option>
                </select>
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Method for splitting documents into chunks
                </p>
              </div>

              <div>
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Max Documents per Batch
                </label>
                <input
                  type="number"
                  name="max_documents_per_batch"
                  min="1"
                  max="1000"
                  defaultValue={settings.max_documents_per_batch}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                />
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Maximum documents to process in one batch (1-1000)
                </p>
              </div>

              <div className="md:col-span-2">
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Embedding Model
                </label>
                <input
                  type="text"
                  name="embedding_model"
                  defaultValue={settings.embedding_model}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                />
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Embedding model to use for document processing
                </p>
              </div>

              <div>
                <label className="block text-redis-sm font-medium text-foreground mb-2">
                  Similarity Threshold
                </label>
                <input
                  type="number"
                  name="similarity_threshold"
                  min="0"
                  max="1"
                  step="0.1"
                  defaultValue={settings.similarity_threshold}
                  className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                />
                <p className="text-redis-xs text-redis-dusk-04 mt-1">
                  Similarity threshold for semantic chunking (0.0-1.0)
                </p>
              </div>

              <div className="md:col-span-2 space-y-4">
                <div className="flex items-center">
                  <input
                    type="checkbox"
                    name="enable_metadata_extraction"
                    id="enable_metadata_extraction"
                    defaultChecked={settings.enable_metadata_extraction}
                    className="h-4 w-4 text-redis-blue-03 focus:ring-redis-blue-03 border-redis-dusk-06 rounded"
                  />
                  <label htmlFor="enable_metadata_extraction" className="ml-2 text-redis-sm text-foreground">
                    Enable metadata extraction from documents
                  </label>
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    name="enable_semantic_chunking"
                    id="enable_semantic_chunking"
                    defaultChecked={settings.enable_semantic_chunking}
                    className="h-4 w-4 text-redis-blue-03 focus:ring-redis-blue-03 border-redis-dusk-06 rounded"
                  />
                  <label htmlFor="enable_semantic_chunking" className="ml-2 text-redis-sm text-foreground">
                    Use semantic chunking instead of fixed-size chunks
                  </label>
                </div>
              </div>
            </div>

            <div className="flex justify-end mt-6">
              <Button type="submit" variant="primary" disabled={isSaving}>
                {isSaving ? <Loader size="sm" /> : 'Save Settings'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-card rounded-lg p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-foreground mb-4">
              Confirm Settings Update
            </h3>
            <p className="text-redis-sm text-redis-dusk-04 mb-6">
              Changing these settings will trigger a new ingestion job to reprocess all documents with the new configuration. This may take some time depending on the size of your knowledge base.
            </p>
            <div className="flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => {
                  setShowConfirmDialog(false);
                  setPendingSettings(null);
                }}
                disabled={isSaving}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={confirmSave}
                disabled={isSaving}
              >
                {isSaving ? <Loader size="sm" /> : 'Update & Re-ingest'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const Settings = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeSection, setActiveSection] = useState(() => {
    return searchParams.get('section') || 'general';
  });

  useEffect(() => {
    const section = searchParams.get('section');
    if (section && ['general', 'instances', 'knowledge', 'notifications', 'security'].includes(section)) {
      setActiveSection(section);
    }
  }, [searchParams]);

  const sections = [
    { id: 'general', label: 'General' },
    { id: 'instances', label: 'Instances' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'security', label: 'Security' },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-redis-xl font-bold text-foreground">Settings</h1>
        <p className="text-redis-sm text-redis-dusk-04 mt-1">
          Configure your Redis SRE Agent preferences and system settings.
        </p>
      </div>

      <div className="flex gap-6">
        {/* Sidebar Navigation */}
        <div className="w-64 flex-shrink-0">
          <Card>
            <CardContent className="p-0">
              <nav className="space-y-1">
                {sections.map((section) => (
                  <button
                    key={section.id}
                    onClick={() => {
                      setActiveSection(section.id);
                      setSearchParams({ section: section.id });
                    }}
                    className={`w-full flex items-center px-4 py-3 text-left text-sm font-medium rounded-none first:rounded-t-lg last:rounded-b-lg transition-colors ${
                      activeSection === section.id
                        ? 'bg-redis-blue-03 text-white'
                        : 'text-foreground hover:bg-redis-dusk-09'
                    }`}
                  >
                    {section.label}
                  </button>
                ))}
              </nav>
            </CardContent>
          </Card>
        </div>

        {/* Main Content */}
        <div className="flex-1">
          {activeSection === 'general' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <h3 className="text-redis-lg font-semibold text-foreground">Agent Configuration</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <label className="text-redis-sm text-foreground font-medium block mb-2">
                        API Endpoint
                      </label>
                      <input
                        type="url"
                        defaultValue="http://localhost:8000"
                        className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                      />
                    </div>
                    <div>
                      <label className="text-redis-sm text-foreground font-medium block mb-2">
                        Response Timeout (seconds)
                      </label>
                      <input
                        type="number"
                        defaultValue="30"
                        className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                      />
                    </div>
                    <Button variant="primary">Save Configuration</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeSection === 'instances' && <Instances />}

          {activeSection === 'knowledge' && <KnowledgeSettingsSection />}

          {activeSection === 'notifications' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <h3 className="text-redis-lg font-semibold text-foreground">Notification Preferences</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">Email Notifications</span>
                      <Button variant="outline" size="sm">Configure</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">Slack Integration</span>
                      <Button variant="outline" size="sm">Setup</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">Alert Thresholds</span>
                      <Button variant="outline" size="sm">Manage</Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {activeSection === 'security' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <h3 className="text-redis-lg font-semibold text-foreground">Security Settings</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">API Authentication</span>
                      <Button variant="outline" size="sm">Configure</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">Access Control</span>
                      <Button variant="outline" size="sm">Manage</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-foreground">Audit Logs</span>
                      <Button variant="outline" size="sm">View</Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
        </div>
      </div>

    </div>
  );
};

export default Settings;
