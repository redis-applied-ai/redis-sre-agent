import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  CollapsibleCard,
  Tooltip,
  CopyIcon,
  type CollapsibleSection
} from '@radar/ui-kit';

// Mock API data
const apiEndpoints = [
  {
    id: 'users',
    method: 'GET',
    path: '/api/v1/users',
    description: 'Retrieve a list of all users',
    parameters: [
      { name: 'page', type: 'number', required: false, description: 'Page number for pagination' },
      { name: 'limit', type: 'number', required: false, description: 'Number of users per page' },
      { name: 'search', type: 'string', required: false, description: 'Search term for filtering users' }
    ],
    response: {
      "users": [
        {
          "id": 1,
          "name": "John Doe",
          "email": "john@example.com",
          "role": "admin",
          "created_at": "2024-01-15T09:30:00Z"
        }
      ],
      "pagination": {
        "page": 1,
        "limit": 10,
        "total": 47,
        "pages": 5
      }
    }
  },
  {
    id: 'create-user',
    method: 'POST',
    path: '/api/v1/users',
    description: 'Create a new user',
    requestBody: {
      "name": "Jane Smith",
      "email": "jane@example.com",
      "role": "user",
      "permissions": ["read", "write"]
    },
    response: {
      "id": 2,
      "name": "Jane Smith",
      "email": "jane@example.com",
      "role": "user",
      "permissions": ["read", "write"],
      "created_at": "2024-03-15T14:22:00Z"
    }
  },
  {
    id: 'deployments',
    method: 'GET',
    path: '/api/v1/deployments',
    description: 'Get all Redis deployments',
    parameters: [
      { name: 'status', type: 'string', required: false, description: 'Filter by deployment status' },
      { name: 'type', type: 'string', required: false, description: 'Filter by deployment type' }
    ],
    response: {
      "deployments": [
        {
          "id": "deploy_123",
          "name": "Production Redis",
          "type": "enterprise",
          "status": "active",
          "host": "redis.example.com",
          "port": 6379,
          "databases": 5,
          "memory_used": "2.1GB",
          "uptime": "99.9%"
        }
      ]
    }
  }
];

const codeExamples = {
  curl: {
    'users': `curl -X GET "https://api.radar.example.com/v1/users?page=1&limit=10" \\
  -H "Authorization: Bearer your_api_token" \\
  -H "Content-Type: application/json"`,
    'create-user': `curl -X POST "https://api.radar.example.com/v1/users" \\
  -H "Authorization: Bearer your_api_token" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Jane Smith",
    "email": "jane@example.com",
    "role": "user",
    "permissions": ["read", "write"]
  }'`,
    'deployments': `curl -X GET "https://api.radar.example.com/v1/deployments" \\
  -H "Authorization: Bearer your_api_token" \\
  -H "Content-Type: application/json"`
  },
  javascript: {
    'users': `const response = await fetch('https://api.radar.example.com/v1/users?page=1&limit=10', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer your_api_token',
    'Content-Type': 'application/json'
  }
});
const data = await response.json();`,
    'create-user': `const response = await fetch('https://api.radar.example.com/v1/users', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your_api_token',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    name: 'Jane Smith',
    email: 'jane@example.com',
    role: 'user',
    permissions: ['read', 'write']
  })
});
const data = await response.json();`,
    'deployments': `const response = await fetch('https://api.radar.example.com/v1/deployments', {
  method: 'GET',
  headers: {
    'Authorization': 'Bearer your_api_token',
    'Content-Type': 'application/json'
  }
});
const data = await response.json();`
  },
  python: {
    'users': `import requests

response = requests.get(
    'https://api.radar.example.com/v1/users',
    params={'page': 1, 'limit': 10},
    headers={
        'Authorization': 'Bearer your_api_token',
        'Content-Type': 'application/json'
    }
)
data = response.json()`,
    'create-user': `import requests

response = requests.post(
    'https://api.radar.example.com/v1/users',
    json={
        'name': 'Jane Smith',
        'email': 'jane@example.com',
        'role': 'user',
        'permissions': ['read', 'write']
    },
    headers={
        'Authorization': 'Bearer your_api_token',
        'Content-Type': 'application/json'
    }
)
data = response.json()`,
    'deployments': `import requests

response = requests.get(
    'https://api.radar.example.com/v1/deployments',
    headers={
        'Authorization': 'Bearer your_api_token',
        'Content-Type': 'application/json'
    }
)
data = response.json()`
  }
};

const ApiDocumentation = () => {
  const [selectedLanguage, setSelectedLanguage] = useState<'curl' | 'javascript' | 'python'>('javascript');
  const [selectedEndpoint, setSelectedEndpoint] = useState(apiEndpoints[0]);
  const [apiKey] = useState('rdr_live_1234567890abcdef1234567890abcdef');
  const [copied, setCopied] = useState<string | null>(null);

  const handleCopy = async (text: string, type: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(type);
      setTimeout(() => setCopied(null), 2000);
    } catch (err) {
      alert('Failed to copy to clipboard');
    }
  };

  const getMethodColor = (method: string) => {
    switch (method) {
      case 'GET': return 'text-redis-green bg-redis-green/20';
      case 'POST': return 'text-redis-blue-03 bg-redis-blue-03/20';
      case 'PUT': return 'text-redis-yellow-500 bg-redis-yellow-500/20';
      case 'DELETE': return 'text-redis-red bg-redis-red/20';
      default: return 'text-redis-dusk-04 bg-redis-dusk-07';
    }
  };

  const authSection: CollapsibleSection = {
    id: 'authentication',
    title: 'Authentication',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div>
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">API Key Authentication</h4>
          <p className="text-redis-sm text-redis-dusk-04 mb-4">
            All API requests require authentication using your API key. Include it in the Authorization header as a Bearer token.
          </p>

          <div className="bg-redis-dusk-09 p-4 rounded-redis-sm">
            <div className="flex items-center justify-between mb-2">
              <span className="text-redis-sm font-medium text-redis-dusk-01">Your API Key</span>
              <Tooltip content={copied === 'api-key' ? 'Copied!' : 'Copy API key'}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleCopy(apiKey, 'api-key')}
                >
                  <CopyIcon className="h-4 w-4" />
                </Button>
              </Tooltip>
            </div>
            <code className="text-redis-xs font-mono text-redis-blue-03 break-all">{apiKey}</code>
          </div>

          <div className="mt-4">
            <h5 className="text-redis-sm font-medium text-redis-dusk-01 mb-2">Example Usage</h5>
            <div className="bg-redis-midnight p-4 rounded-redis-sm">
              <code className="text-redis-xs text-redis-dusk-01 font-mono">
                Authorization: Bearer {apiKey}
              </code>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-redis-dusk-08">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Rate Limits</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 border border-redis-dusk-08 rounded-redis-sm">
              <p className="text-redis-sm font-medium text-redis-dusk-01">Standard Plan</p>
              <p className="text-redis-xs text-redis-dusk-04">1,000 requests per hour</p>
            </div>
            <div className="p-4 border border-redis-dusk-08 rounded-redis-sm">
              <p className="text-redis-sm font-medium text-redis-dusk-01">Premium Plan</p>
              <p className="text-redis-xs text-redis-dusk-04">10,000 requests per hour</p>
            </div>
          </div>
        </div>
      </div>
    )
  };

  const endpointsSection: CollapsibleSection = {
    id: 'endpoints',
    title: 'API Endpoints',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Endpoint List */}
          <div className="lg:col-span-1">
            <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Endpoints</h4>
            <div className="space-y-2">
              {apiEndpoints.map((endpoint) => (
                <button
                  key={endpoint.id}
                  onClick={() => setSelectedEndpoint(endpoint)}
                  className={`w-full text-left p-3 rounded-redis-sm border transition-colors ${
                    selectedEndpoint.id === endpoint.id
                      ? 'border-redis-blue-03 bg-redis-blue-03/10'
                      : 'border-redis-dusk-08 hover:border-redis-dusk-07'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getMethodColor(endpoint.method)}`}>
                      {endpoint.method}
                    </span>
                    <span className="text-redis-xs font-mono text-redis-dusk-04">{endpoint.path}</span>
                  </div>
                  <p className="text-redis-xs text-redis-dusk-04">{endpoint.description}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Endpoint Details */}
          <div className="lg:col-span-2">
            <div className="space-y-6">
              <div>
                <div className="flex items-center gap-3 mb-4">
                  <span className={`px-3 py-1 rounded-redis-sm text-redis-sm font-medium ${getMethodColor(selectedEndpoint.method)}`}>
                    {selectedEndpoint.method}
                  </span>
                  <code className="text-redis-sm font-mono text-redis-dusk-01">{selectedEndpoint.path}</code>
                </div>
                <p className="text-redis-sm text-redis-dusk-04">{selectedEndpoint.description}</p>
              </div>

              {/* Parameters */}
              {selectedEndpoint.parameters && (
                <div>
                  <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Parameters</h5>
                  <div className="space-y-2">
                    {selectedEndpoint.parameters.map((param, index) => (
                      <div key={index} className="flex items-center justify-between p-3 bg-redis-dusk-09 rounded-redis-sm">
                        <div>
                          <div className="flex items-center gap-2">
                            <code className="text-redis-sm font-mono text-redis-blue-03">{param.name}</code>
                            <span className="text-redis-xs text-redis-dusk-04">({param.type})</span>
                            {param.required && (
                              <span className="text-redis-xs text-redis-red bg-redis-red/20 px-2 py-1 rounded-redis-xs">
                                required
                              </span>
                            )}
                          </div>
                          <p className="text-redis-xs text-redis-dusk-04 mt-1">{param.description}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Request Body */}
              {selectedEndpoint.requestBody && (
                <div>
                  <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Request Body</h5>
                  <div className="bg-redis-midnight p-4 rounded-redis-sm">
                    <pre className="text-redis-xs text-redis-dusk-01 font-mono overflow-x-auto">
                      {JSON.stringify(selectedEndpoint.requestBody, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* Response */}
              <div>
                <h5 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Response</h5>
                <div className="bg-redis-midnight p-4 rounded-redis-sm">
                  <pre className="text-redis-xs text-redis-dusk-01 font-mono overflow-x-auto">
                    {JSON.stringify(selectedEndpoint.response, null, 2)}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  };

  const codeExamplesSection: CollapsibleSection = {
    id: 'examples',
    title: 'Code Examples',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center gap-2">
          <span className="text-redis-sm font-medium text-redis-dusk-01">Language:</span>
          <div className="flex gap-2">
            {(['curl', 'javascript', 'python'] as const).map((lang) => (
              <Button
                key={lang}
                variant={selectedLanguage === lang ? 'primary' : 'outline'}
                size="sm"
                onClick={() => setSelectedLanguage(lang)}
              >
                {lang === 'curl' ? 'cURL' : lang === 'javascript' ? 'JavaScript' : 'Python'}
              </Button>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          {apiEndpoints.map((endpoint) => (
            <div key={endpoint.id}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getMethodColor(endpoint.method)}`}>
                    {endpoint.method}
                  </span>
                  <code className="text-redis-sm font-mono text-redis-dusk-01">{endpoint.path}</code>
                </div>
                <Tooltip content={copied === `${endpoint.id}-${selectedLanguage}` ? 'Copied!' : 'Copy code'}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy(codeExamples[selectedLanguage][endpoint.id as keyof typeof codeExamples.curl], `${endpoint.id}-${selectedLanguage}`)}
                  >
                    <CopyIcon className="h-4 w-4" />
                  </Button>
                </Tooltip>
              </div>
              <div className="bg-redis-midnight p-4 rounded-redis-sm">
                <pre className="text-redis-xs text-redis-dusk-01 font-mono overflow-x-auto">
                  {codeExamples[selectedLanguage][endpoint.id as keyof typeof codeExamples.curl]}
                </pre>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  };

  const errorHandlingSection: CollapsibleSection = {
    id: 'errors',
    title: 'Error Handling',
    icon: <div className="h-4 w-4 bg-redis-red rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div>
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">HTTP Status Codes</h4>
          <div className="space-y-3">
            {[
              { code: '200', status: 'OK', description: 'Request successful' },
              { code: '201', status: 'Created', description: 'Resource created successfully' },
              { code: '400', status: 'Bad Request', description: 'Invalid request parameters' },
              { code: '401', status: 'Unauthorized', description: 'Invalid or missing API key' },
              { code: '403', status: 'Forbidden', description: 'Insufficient permissions' },
              { code: '404', status: 'Not Found', description: 'Resource not found' },
              { code: '429', status: 'Too Many Requests', description: 'Rate limit exceeded' },
              { code: '500', status: 'Internal Server Error', description: 'Server error occurred' }
            ].map((error) => (
              <div key={error.code} className="flex items-center justify-between p-3 border border-redis-dusk-08 rounded-redis-sm">
                <div className="flex items-center gap-3">
                  <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-mono ${
                    error.code.startsWith('2') ? 'text-redis-green bg-redis-green/20' :
                    error.code.startsWith('4') ? 'text-redis-yellow-500 bg-redis-yellow-500/20' :
                    'text-redis-red bg-redis-red/20'
                  }`}>
                    {error.code}
                  </span>
                  <span className="text-redis-sm font-medium text-redis-dusk-01">{error.status}</span>
                </div>
                <span className="text-redis-sm text-redis-dusk-04">{error.description}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01 mb-4">Error Response Format</h4>
          <div className="bg-redis-midnight p-4 rounded-redis-sm">
            <pre className="text-redis-xs text-redis-dusk-01 font-mono">
{`{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid email address format",
    "details": {
      "field": "email",
      "value": "invalid-email"
    },
    "request_id": "req_1234567890"
  }
}`}
            </pre>
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
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">API Documentation</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Complete reference for the Radar API with examples and guides
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Download SDK</Button>
          <Button variant="primary">Get API Key</Button>
        </div>
      </div>

      {/* API Overview */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">API Overview</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-2">Base URL</h4>
              <div className="flex items-center gap-2">
                <code className="text-redis-sm bg-redis-dusk-09 px-3 py-2 rounded-redis-sm font-mono flex-1">
                  https://api.radar.example.com/v1
                </code>
                <Tooltip content={copied === 'base-url' ? 'Copied!' : 'Copy URL'}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy('https://api.radar.example.com/v1', 'base-url')}
                  >
                    <CopyIcon className="h-4 w-4" />
                  </Button>
                </Tooltip>
              </div>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-2">Content Type</h4>
              <code className="text-redis-sm bg-redis-dusk-09 px-3 py-2 rounded-redis-sm font-mono block">
                application/json
              </code>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-2">API Version</h4>
              <code className="text-redis-sm bg-redis-dusk-09 px-3 py-2 rounded-redis-sm font-mono block">
                v1
              </code>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* API Sections */}
      <CollapsibleCard
        title="API Reference"
        description="Complete documentation for all API endpoints and authentication"
        sections={[authSection, endpointsSection, codeExamplesSection, errorHandlingSection]}
        defaultExpandedSection="authentication"
        allowMultipleExpanded={true}
      />
    </div>
  );
};

export default ApiDocumentation;
