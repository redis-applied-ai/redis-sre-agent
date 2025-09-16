import {
  Card,
  CardHeader,
  CardContent,
  Button,
} from '@radar/ui-kit';

const Settings = () => {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-redis-xl font-bold text-redis-dusk-01">Settings</h1>
        <p className="text-redis-sm text-redis-dusk-04 mt-1">
          Configure your Redis SRE Agent preferences and system settings.
        </p>
      </div>

      {/* Settings Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
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
                  className="redis-input-base w-full"
                />
              </div>
              <div>
                <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                  Response Timeout (seconds)
                </label>
                <input
                  type="number"
                  defaultValue="30"
                  className="redis-input-base w-full"
                />
              </div>
              <Button variant="primary">Save Configuration</Button>
            </div>
          </CardContent>
        </Card>

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
    </div>
  );
};

export default Settings;
