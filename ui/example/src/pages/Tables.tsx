import { useState, useMemo } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  Avatar,
  DropdownMenu,
  Pagination,
  CollapsibleCard,
  Tooltip,
  type DropdownMenuItem,
  type CollapsibleSection
} from '@radar/ui-kit';

// Mock data
const generateMockData = (count: number) => {
  const statuses = ['active', 'inactive', 'pending', 'suspended'];
  const roles = ['admin', 'user', 'viewer', 'manager'];
  const departments = ['Engineering', 'Marketing', 'Sales', 'Support', 'HR'];

  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    name: `User ${i + 1}`,
    email: `user${i + 1}@example.com`,
    role: roles[i % roles.length],
    department: departments[i % departments.length],
    status: statuses[i % statuses.length],
    lastLogin: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000),
    createdAt: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
    loginCount: Math.floor(Math.random() * 500) + 10,
    score: Math.floor(Math.random() * 100),
    isVerified: Math.random() > 0.3
  }));
};

const deploymentData = Array.from({ length: 25 }, (_, i) => ({
  id: `deploy_${i + 1}`,
  name: `Redis Instance ${i + 1}`,
  environment: ['production', 'staging', 'development'][i % 3],
  status: ['healthy', 'warning', 'critical', 'offline'][i % 4],
  region: ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-south-1'][i % 4],
  version: ['7.2.4', '7.0.15', '6.2.14'][i % 3],
  uptime: `${(Math.random() * 100).toFixed(2)}%`,
  memory: `${(Math.random() * 8).toFixed(1)}GB`,
  connections: Math.floor(Math.random() * 1000) + 50,
  operations: Math.floor(Math.random() * 50000) + 10000,
  lastBackup: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000)
}));

const Tables = () => {
  const [userData] = useState(generateMockData(100));
  const [sortField, setSortField] = useState<string>('name');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [selectedRows, setSelectedRows] = useState<Set<number>>(new Set());

  // Deployment table state
  const [deploymentSortField, setDeploymentSortField] = useState<string>('name');
  const [deploymentSortDirection, setDeploymentSortDirection] = useState<'asc' | 'desc'>('asc');
  const [deploymentSearch, setDeploymentSearch] = useState('');
  const [deploymentStatusFilter, setDeploymentStatusFilter] = useState<string>('all');

  // Filter and sort data
  const filteredAndSortedData = useMemo(() => {
    let filtered = userData.filter(user => {
      const matchesSearch = user.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           user.email.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus = statusFilter === 'all' || user.status === statusFilter;
      const matchesRole = roleFilter === 'all' || user.role === roleFilter;
      return matchesSearch && matchesStatus && matchesRole;
    });

    return filtered.sort((a, b) => {
      const aValue = a[sortField as keyof typeof a];
      const bValue = b[sortField as keyof typeof b];

      if (aValue < bValue) return sortDirection === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [userData, searchTerm, statusFilter, roleFilter, sortField, sortDirection]);

  // Filter deployment data
  const filteredDeploymentData = useMemo(() => {
    let filtered = deploymentData.filter(deployment => {
      const matchesSearch = deployment.name.toLowerCase().includes(deploymentSearch.toLowerCase()) ||
                           deployment.environment.toLowerCase().includes(deploymentSearch.toLowerCase());
      const matchesStatus = deploymentStatusFilter === 'all' || deployment.status === deploymentStatusFilter;
      return matchesSearch && matchesStatus;
    });

    return filtered.sort((a, b) => {
      const aValue = a[deploymentSortField as keyof typeof a];
      const bValue = b[deploymentSortField as keyof typeof b];

      if (aValue < bValue) return deploymentSortDirection === 'asc' ? -1 : 1;
      if (aValue > bValue) return deploymentSortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [deploymentData, deploymentSearch, deploymentStatusFilter, deploymentSortField, deploymentSortDirection]);

  // Pagination
  const totalPages = Math.ceil(filteredAndSortedData.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const currentData = filteredAndSortedData.slice(startIndex, startIndex + pageSize);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const handleDeploymentSort = (field: string) => {
    if (deploymentSortField === field) {
      setDeploymentSortDirection(deploymentSortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setDeploymentSortField(field);
      setDeploymentSortDirection('asc');
    }
  };

  const handleSelectRow = (id: number) => {
    const newSelected = new Set(selectedRows);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedRows(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedRows.size === currentData.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(currentData.map(item => item.id)));
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'active':
      case 'healthy': return 'text-redis-green bg-redis-green/20';
      case 'warning': return 'text-redis-yellow-500 bg-redis-yellow-500/20';
      case 'critical': return 'text-redis-red bg-redis-red/20';
      case 'inactive':
      case 'offline': return 'text-redis-dusk-04 bg-redis-dusk-07';
      case 'pending': return 'text-redis-blue-03 bg-redis-blue-03/20';
      case 'suspended': return 'text-redis-red bg-redis-red/20';
      default: return 'text-redis-dusk-04 bg-redis-dusk-07';
    }
  };

  const getUserActions = (user: any): DropdownMenuItem[] => [
    {
      label: 'View Profile',
      onClick: () => alert(`Viewing ${user.name}'s profile`)
    },
    {
      label: 'Edit User',
      onClick: () => alert(`Editing ${user.name}`)
    },
    {
      label: 'Send Message',
      onClick: () => alert(`Sending message to ${user.email}`)
    },
    {
      label: 'Reset Password',
      onClick: () => alert(`Resetting password for ${user.email}`)
    },
    {
      label: user.status === 'active' ? 'Deactivate' : 'Activate',
      onClick: () => alert(`${user.status === 'active' ? 'Deactivating' : 'Activating'} ${user.name}`)
    },
    {
      label: 'Delete User',
      onClick: () => {
        if (confirm(`Are you sure you want to delete ${user.name}?`)) {
          alert(`${user.name} would be deleted`);
        }
      },
      variant: 'destructive'
    }
  ];

  const getDeploymentActions = (deployment: any): DropdownMenuItem[] => [
    {
      label: 'View Details',
      onClick: () => alert(`Viewing ${deployment.name} details`)
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
      label: 'Edit Configuration',
      onClick: () => alert(`Editing ${deployment.name} configuration`)
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

  const SortableHeader = ({ field, children, className = '' }: { field: string, children: React.ReactNode, className?: string }) => (
    <button
      onClick={() => handleSort(field)}
      className={`flex items-center gap-1 text-left ${className}`}
    >
      {children}
      <span className="text-redis-xs">
        {sortField === field ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </button>
  );

  const DeploymentSortableHeader = ({ field, children, className = '' }: { field: string, children: React.ReactNode, className?: string }) => (
    <button
      onClick={() => handleDeploymentSort(field)}
      className={`flex items-center gap-1 text-left ${className}`}
    >
      {children}
      <span className="text-redis-xs">
        {deploymentSortField === field ? (deploymentSortDirection === 'asc' ? '↑' : '↓') : '↕'}
      </span>
    </button>
  );

  const basicTableSection: CollapsibleSection = {
    id: 'basic',
    title: 'Basic Data Table',
    icon: <div className="h-4 w-4 bg-redis-blue-03 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            User Management Table
          </h4>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">Export CSV</Button>
            <Button variant="primary" size="sm">Add User</Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-64">
            <Input
              placeholder="Search users..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="redis-input-base"
          >
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="inactive">Inactive</option>
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
          </select>
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="redis-input-base"
          >
            <option value="all">All Roles</option>
            <option value="admin">Admin</option>
            <option value="user">User</option>
            <option value="viewer">Viewer</option>
            <option value="manager">Manager</option>
          </select>
        </div>

        {/* Bulk Actions */}
        {selectedRows.size > 0 && (
          <div className="flex items-center gap-4 p-3 bg-redis-blue-03/10 border border-redis-blue-03/30 rounded-redis-sm">
            <span className="text-redis-sm text-redis-dusk-01">
              {selectedRows.size} row{selectedRows.size !== 1 ? 's' : ''} selected
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm">Export Selected</Button>
              <Button variant="outline" size="sm">Bulk Edit</Button>
              <Button variant="destructive" size="sm">Delete Selected</Button>
            </div>
          </div>
        )}

        {/* Table */}
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-redis-dusk-09 border-b border-redis-dusk-08">
                  <tr>
                    <th className="p-4 text-left">
                      <input
                        type="checkbox"
                        checked={selectedRows.size === currentData.length && currentData.length > 0}
                        onChange={handleSelectAll}
                        className="rounded border-redis-dusk-08"
                      />
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="name" className="text-redis-xs font-medium text-redis-dusk-04">
                        USER
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="role" className="text-redis-xs font-medium text-redis-dusk-04">
                        ROLE
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="department" className="text-redis-xs font-medium text-redis-dusk-04">
                        DEPARTMENT
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="status" className="text-redis-xs font-medium text-redis-dusk-04">
                        STATUS
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="lastLogin" className="text-redis-xs font-medium text-redis-dusk-04">
                        LAST LOGIN
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <SortableHeader field="loginCount" className="text-redis-xs font-medium text-redis-dusk-04">
                        LOGINS
                      </SortableHeader>
                    </th>
                    <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">
                      ACTIONS
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-redis-dusk-08">
                  {currentData.map((user) => (
                    <tr key={user.id} className="hover:bg-redis-dusk-09 transition-colors">
                      <td className="p-4">
                        <input
                          type="checkbox"
                          checked={selectedRows.has(user.id)}
                          onChange={() => handleSelectRow(user.id)}
                          className="rounded border-redis-dusk-08"
                        />
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <Avatar fallback={user.name} size="sm" />
                          <div>
                            <div className="text-redis-sm font-medium text-redis-dusk-01">
                              {user.name}
                            </div>
                            <div className="text-redis-xs text-redis-dusk-04">
                              {user.email}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                          user.role === 'admin'
                            ? 'bg-redis-red/20 text-redis-red'
                            : user.role === 'manager'
                            ? 'bg-redis-blue-03/20 text-redis-blue-03'
                            : 'bg-redis-dusk-07 text-redis-dusk-04'
                        }`}>
                          {user.role}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {user.department}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getStatusColor(user.status)}`}>
                          {user.status}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {user.lastLogin.toLocaleDateString()}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {user.loginCount.toLocaleString()}
                        </span>
                      </td>
                      <td className="p-4">
                        <DropdownMenu
                          trigger={
                            <Button variant="ghost" size="sm">
                              <span className="text-redis-dusk-04">⋯</span>
                            </Button>
                          }
                          items={getUserActions(user)}
                          placement="bottom-right"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>

          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            itemCount={filteredAndSortedData.length}
            itemLabel="users"
            pageSize={pageSize}
            pageSizeOptions={[5, 10, 25, 50, 100]}
            onPageChange={setCurrentPage}
            onPageSizeChange={(size) => {
              setPageSize(size);
              setCurrentPage(1);
            }}
          />
        </Card>
      </div>
    )
  };

  const deploymentTableSection: CollapsibleSection = {
    id: 'deployments',
    title: 'Advanced Deployment Table',
    icon: <div className="h-4 w-4 bg-redis-green rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
            Redis Deployments
          </h4>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">Refresh All</Button>
            <Button variant="primary" size="sm">New Deployment</Button>
          </div>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-64">
            <Input
              placeholder="Search deployments..."
              value={deploymentSearch}
              onChange={(e) => setDeploymentSearch(e.target.value)}
            />
          </div>
          <select
            value={deploymentStatusFilter}
            onChange={(e) => setDeploymentStatusFilter(e.target.value)}
            className="redis-input-base"
          >
            <option value="all">All Statuses</option>
            <option value="healthy">Healthy</option>
            <option value="warning">Warning</option>
            <option value="critical">Critical</option>
            <option value="offline">Offline</option>
          </select>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[
            { label: 'Total Deployments', value: deploymentData.length, color: 'redis-blue-03' },
            { label: 'Healthy', value: deploymentData.filter(d => d.status === 'healthy').length, color: 'redis-green' },
            { label: 'Warnings', value: deploymentData.filter(d => d.status === 'warning').length, color: 'redis-yellow-500' },
            { label: 'Critical', value: deploymentData.filter(d => d.status === 'critical').length, color: 'redis-red' }
          ].map((stat, index) => (
            <div key={index} className="p-4 bg-redis-dusk-09 rounded-redis-sm">
              <div className="text-redis-xs text-redis-dusk-04 font-medium mb-1">
                {stat.label}
              </div>
              <div className={`text-redis-lg font-bold text-${stat.color}`}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        {/* Table */}
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-redis-dusk-09 border-b border-redis-dusk-08">
                  <tr>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="name" className="text-redis-xs font-medium text-redis-dusk-04">
                        DEPLOYMENT
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="environment" className="text-redis-xs font-medium text-redis-dusk-04">
                        ENVIRONMENT
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="status" className="text-redis-xs font-medium text-redis-dusk-04">
                        STATUS
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="region" className="text-redis-xs font-medium text-redis-dusk-04">
                        REGION
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="memory" className="text-redis-xs font-medium text-redis-dusk-04">
                        MEMORY
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="connections" className="text-redis-xs font-medium text-redis-dusk-04">
                        CONNECTIONS
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="operations" className="text-redis-xs font-medium text-redis-dusk-04">
                        OPS/SEC
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left">
                      <DeploymentSortableHeader field="uptime" className="text-redis-xs font-medium text-redis-dusk-04">
                        UPTIME
                      </DeploymentSortableHeader>
                    </th>
                    <th className="p-4 text-left text-redis-xs font-medium text-redis-dusk-04">
                      ACTIONS
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-redis-dusk-08">
                  {filteredDeploymentData.map((deployment) => (
                    <tr key={deployment.id} className="hover:bg-redis-dusk-09 transition-colors">
                      <td className="p-4">
                        <div>
                          <div className="text-redis-sm font-medium text-redis-dusk-01">
                            {deployment.name}
                          </div>
                          <div className="text-redis-xs text-redis-dusk-04">
                            {deployment.version}
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                          deployment.environment === 'production'
                            ? 'bg-redis-red/20 text-redis-red'
                            : deployment.environment === 'staging'
                            ? 'bg-redis-yellow-500/20 text-redis-yellow-500'
                            : 'bg-redis-blue-03/20 text-redis-blue-03'
                        }`}>
                          {deployment.environment}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-2">
                          <div className={`w-2 h-2 rounded-full ${
                            deployment.status === 'healthy' ? 'bg-redis-green' :
                            deployment.status === 'warning' ? 'bg-redis-yellow-500' :
                            deployment.status === 'critical' ? 'bg-redis-red' :
                            'bg-redis-dusk-04'
                          }`} />
                          <span className="text-redis-sm text-redis-dusk-01 capitalize">
                            {deployment.status}
                          </span>
                        </div>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {deployment.region}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {deployment.memory}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {deployment.connections.toLocaleString()}
                        </span>
                      </td>
                      <td className="p-4">
                        <span className="text-redis-sm text-redis-dusk-04">
                          {deployment.operations.toLocaleString()}
                        </span>
                      </td>
                      <td className="p-4">
                        <Tooltip content={`Last backup: ${deployment.lastBackup.toLocaleDateString()}`}>
                          <span className={`text-redis-sm ${
                            parseFloat(deployment.uptime) > 99 ? 'text-redis-green' :
                            parseFloat(deployment.uptime) > 95 ? 'text-redis-yellow-500' :
                            'text-redis-red'
                          }`}>
                            {deployment.uptime}
                          </span>
                        </Tooltip>
                      </td>
                      <td className="p-4">
                        <DropdownMenu
                          trigger={
                            <Button variant="ghost" size="sm">
                              <span className="text-redis-dusk-04">⋯</span>
                            </Button>
                          }
                          items={getDeploymentActions(deployment)}
                          placement="bottom-right"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  };

  const compactTableSection: CollapsibleSection = {
    id: 'compact',
    title: 'Compact Table Views',
    icon: <div className="h-4 w-4 bg-redis-yellow-500 rounded-full" />,
    content: (
      <div className="p-6 space-y-6">
        <h4 className="text-redis-lg font-semibold text-redis-dusk-01">
          Mobile-Friendly Compact Tables
        </h4>

        {/* Compact User List */}
        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">Recent Users (Compact)</h5>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-redis-dusk-08">
              {currentData.slice(0, 5).map((user) => (
                <div key={user.id} className="p-3 hover:bg-redis-dusk-09 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <Avatar fallback={user.name} size="sm" />
                      <div>
                        <div className="text-redis-sm font-medium text-redis-dusk-01">
                          {user.name}
                        </div>
                        <div className="text-redis-xs text-redis-dusk-04">
                          {user.role} • {user.department}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${getStatusColor(user.status)}`}>
                        {user.status}
                      </span>
                      <DropdownMenu
                        trigger={
                          <Button variant="ghost" size="sm">
                            <span className="text-redis-dusk-04">⋯</span>
                          </Button>
                        }
                        items={getUserActions(user)}
                        placement="bottom-right"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Key-Value Table */}
        <Card>
          <CardHeader>
            <h5 className="text-redis-sm font-semibold text-redis-dusk-01">System Information</h5>
          </CardHeader>
          <CardContent className="p-0">
            <div className="divide-y divide-redis-dusk-08">
              {[
                { key: 'Total Memory', value: '16.0 GB' },
                { key: 'Available Memory', value: '8.2 GB' },
                { key: 'CPU Cores', value: '8' },
                { key: 'Load Average', value: '2.14' },
                { key: 'Disk Usage', value: '67% (2.1TB / 3.2TB)' },
                { key: 'Network I/O', value: '1.2 GB/s' },
                { key: 'Uptime', value: '14 days, 6 hours' },
                { key: 'Redis Version', value: '7.2.4' }
              ].map((item, index) => (
                <div key={index} className="flex items-center justify-between p-3">
                  <span className="text-redis-sm text-redis-dusk-04">{item.key}</span>
                  <span className="text-redis-sm font-medium text-redis-dusk-01">{item.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    )
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Tables</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Comprehensive table examples with sorting, filtering, pagination, and actions
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Table Settings</Button>
          <Button variant="primary">Create Table</Button>
        </div>
      </div>

      {/* Table Examples */}
      <CollapsibleCard
        title="Table Examples"
        description="Different table patterns and configurations for various use cases"
        sections={[basicTableSection, deploymentTableSection, compactTableSection]}
        defaultExpandedSection="basic"
        allowMultipleExpanded={false}
      />

      {/* Table Best Practices */}
      <Card>
        <CardHeader>
          <h3 className="text-redis-lg font-semibold text-redis-dusk-01">Table Design Guidelines</h3>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Performance</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Use pagination for large datasets (100+ rows)</li>
                <li>• Implement virtual scrolling for 1000+ items</li>
                <li>• Debounce search and filter inputs</li>
                <li>• Cache sorted/filtered results when possible</li>
                <li>• Use React.memo for row components</li>
              </ul>
            </div>
            <div>
              <h4 className="text-redis-sm font-semibold text-redis-dusk-01 mb-3">Accessibility</h4>
              <ul className="space-y-2 text-redis-sm text-redis-dusk-04">
                <li>• Use semantic table elements (thead, tbody, etc.)</li>
                <li>• Provide clear column headers and sorting indicators</li>
                <li>• Ensure keyboard navigation works properly</li>
                <li>• Use ARIA labels for complex interactions</li>
                <li>• Maintain focus management for actions</li>
              </ul>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

export default Tables;
