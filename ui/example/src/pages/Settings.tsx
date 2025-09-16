import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  Form,
  CollapsibleCard,
  Tooltip,
  CopyIcon,
  type FormFieldConfig,
  type CollapsibleSection
} from '@radar/ui-kit';

const Settings = () => {
  const [apiKey] = useState('demo_key_1234567890abcdef1234567890abcdef');
  const [copied, setCopied] = useState(false);

  const profileFormFields: FormFieldConfig[] = [
    {
      name: 'name',
      label: 'Full Name',
      type: 'text',
      required: true
    },
    {
      name: 'email',
      label: 'Email Address',
      type: 'email',
      required: true
    },
    {
      name: 'timezone',
      label: 'Timezone',
      type: 'select',
      options: [
        { label: 'UTC', value: 'utc' },
        { label: 'Eastern Time', value: 'est' },
        { label: 'Pacific Time', value: 'pst' },
        { label: 'Central Time', value: 'cst' }
      ]
    }
  ];

  const securityFormFields: FormFieldConfig[] = [
    {
      name: 'currentPassword',
      label: 'Current Password',
      type: 'password',
      required: true
    },
    {
      name: 'newPassword',
      label: 'New Password',
      type: 'password',
      required: true,
      validation: (value) =>
        value.length < 8 ? 'Password must be at least 8 characters' : undefined
    },
    {
      name: 'confirmPassword',
      label: 'Confirm New Password',
      type: 'password',
      required: true
    }
  ];

  const handleCopyApiKey = async () => {
    try {
      await navigator.clipboard.writeText(apiKey);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      alert('Failed to copy API key');
    }
  };

  const handleProfileUpdate = async (data: Record<string, any>) => {
    console.log('Updating profile:', data);
    await new Promise(resolve => setTimeout(resolve, 1000));
    alert('Profile updated successfully!');
  };

  const handlePasswordChange = async (data: Record<string, any>) => {
    console.log('Changing password:', data);

    if (data.newPassword !== data.confirmPassword) {
      throw new Error('Passwords do not match');
    }

    await new Promise(resolve => setTimeout(resolve, 1000));
    alert('Password changed successfully!');
  };

  const configurationSections: CollapsibleSection[] = [
    {
      id: 'profile',
      title: 'Profile Information',
      icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
      content: (
        <div className="p-6">
          <Form
            fields={profileFormFields}
            initialData={{
              name: 'John Doe',
              email: 'john.doe@example.com',
              timezone: 'est'
            }}
            onSubmit={handleProfileUpdate}
            submitLabel="Update Profile"
            layout="vertical"
          />
        </div>
      )
    },
    {
      id: 'security',
      title: 'Security Settings',
      icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
      content: (
        <div className="p-6 space-y-6">
          <div>
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">
              Change Password
            </h4>
            <Form
              fields={securityFormFields}
              onSubmit={handlePasswordChange}
              submitLabel="Change Password"
              layout="vertical"
            />
          </div>

          <div className="pt-6 border-t border-redis-dusk-08">
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">
              Two-Factor Authentication
            </h4>
            <div className="flex items-center justify-between p-4 border border-redis-dusk-08 rounded-redis-sm">
              <div>
                <p className="text-redis-sm font-medium text-redis-dusk-01">
                  Authenticator App
                </p>
                <p className="text-redis-xs text-redis-dusk-04">
                  Not configured
                </p>
              </div>
              <Button variant="outline">Setup</Button>
            </div>
          </div>
        </div>
      )
    },
    {
      id: 'api',
      title: 'API Configuration',
      icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
      content: (
        <div className="p-6 space-y-6">
          <div>
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">
              API Keys
            </h4>
            <div className="space-y-4">
              <div className="p-4 border border-redis-dusk-08 rounded-redis-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-redis-sm font-medium text-redis-dusk-01">
                    Primary API Key
                  </span>
                  <span className="text-redis-xs text-redis-green bg-redis-green/20 px-2 py-1 rounded-redis-xs">
                    Active
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    value={apiKey}
                    readOnly
                    className="font-mono text-redis-xs"
                  />
                  <Tooltip content={copied ? 'Copied!' : 'Copy API key'}>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopyApiKey}
                    >
                      <CopyIcon className="h-4 w-4" />
                    </Button>
                  </Tooltip>
                </div>
                <p className="text-redis-xs text-redis-dusk-04 mt-2">
                  Created on March 15, 2024 • Last used 2 hours ago
                </p>
              </div>
              <Button variant="outline">Generate New Key</Button>
            </div>
          </div>

          <div className="pt-6 border-t border-redis-dusk-08">
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">
              Rate Limiting
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                  Requests per minute
                </label>
                <Input type="number" defaultValue="100" />
              </div>
              <div>
                <label className="text-redis-sm text-redis-dusk-01 font-medium block mb-2">
                  Requests per hour
                </label>
                <Input type="number" defaultValue="5000" />
              </div>
            </div>
            <Button variant="primary" className="mt-4">Save Limits</Button>
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
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Settings</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Manage your account settings and preferences
          </p>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-xs text-redis-dusk-04 font-medium">Account Type</p>
                <p className="text-redis-lg font-bold text-redis-dusk-01 mt-1">Premium</p>
              </div>
              <div className="h-8 w-8 bg-redis-blue-03 rounded-full flex items-center justify-center">
                <span className="text-white text-redis-xs">P</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-xs text-redis-dusk-04 font-medium">API Calls Today</p>
                <p className="text-redis-lg font-bold text-redis-dusk-01 mt-1">2,847</p>
              </div>
              <div className="h-8 w-8 bg-redis-green rounded-full flex items-center justify-center">
                <span className="text-white text-redis-xs">↗</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-redis-xs text-redis-dusk-04 font-medium">Storage Used</p>
                <p className="text-redis-lg font-bold text-redis-dusk-01 mt-1">67%</p>
              </div>
              <div className="h-8 w-8 bg-redis-yellow-500 rounded-full flex items-center justify-center">
                <span className="text-black text-redis-xs">!</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Settings Sections */}
      <CollapsibleCard
        title="Account Settings"
        description="Configure your profile, security, and API settings"
        sections={configurationSections}
        defaultExpandedSection="profile"
        allowMultipleExpanded={false}
      />

      {/* Danger Zone */}
      <Card className="border-redis-red/50">
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-red">Danger Zone</h3>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 border border-redis-red/30 rounded-redis-sm">
              <div>
                <p className="text-redis-sm font-medium text-redis-dusk-01">
                  Export Account Data
                </p>
                <p className="text-redis-xs text-redis-dusk-04">
                  Download all your account data in JSON format
                </p>
              </div>
              <Button variant="outline">Export Data</Button>
            </div>

            <div className="flex items-center justify-between p-4 border border-redis-red/30 rounded-redis-sm">
              <div>
                <p className="text-redis-sm font-medium text-redis-red">
                  Delete Account
                </p>
                <p className="text-redis-xs text-redis-dusk-04">
                  Permanently delete your account and all data
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={() => {
                  if (confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
                    alert('Account deletion would be processed');
                  }
                }}
              >
                Delete Account
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Settings;
