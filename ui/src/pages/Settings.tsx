import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
} from '@radar/ui-kit';
import Instances from './Instances';

const Settings = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeSection, setActiveSection] = useState(() => {
    return searchParams.get('section') || 'general';
  });

  useEffect(() => {
    const section = searchParams.get('section');
    if (section && ['general', 'instances', 'notifications', 'security'].includes(section)) {
      setActiveSection(section);
    }
  }, [searchParams]);

  const sections = [
    { id: 'general', label: 'General' },
    { id: 'instances', label: 'Instances' },
    { id: 'notifications', label: 'Notifications' },
    { id: 'security', label: 'Security' },
  ];

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-redis-xl font-bold text-redis-dusk-01">Settings</h1>
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
                        : 'text-redis-dusk-01 hover:bg-redis-dusk-09'
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
                  <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Agent Configuration</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div>
                      <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                        API Endpoint
                      </label>
                      <input
                        type="url"
                        defaultValue="http://localhost:8000"
                        className="w-full px-3 py-2 border border-redis-dusk-06 rounded-redis-sm focus:outline-none focus:ring-2 focus:ring-redis-blue-03"
                      />
                    </div>
                    <div>
                      <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
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

          {activeSection === 'notifications' && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Notification Preferences</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">Email Notifications</span>
                      <Button variant="outline" size="sm">Configure</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">Slack Integration</span>
                      <Button variant="outline" size="sm">Setup</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">Alert Thresholds</span>
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
                  <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Security Settings</h3>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">API Authentication</span>
                      <Button variant="outline" size="sm">Configure</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">Access Control</span>
                      <Button variant="outline" size="sm">Manage</Button>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-redis-sm text-redis-dusk-01">Audit Logs</span>
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
