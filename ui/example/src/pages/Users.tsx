import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardContent,
  Button,
  Input,
  Pagination,
  Form,
  Avatar,
  DropdownMenu,
  ErrorMessage,
  type FormFieldConfig,
  type DropdownMenuItem
} from '@radar/ui-kit';

// Mock data
const mockUsers = Array.from({ length: 47 }, (_, i) => ({
  id: i + 1,
  name: `User ${i + 1}`,
  email: `user${i + 1}@example.com`,
  role: ['Admin', 'User', 'Viewer'][i % 3],
  status: ['Active', 'Inactive'][i % 2],
  lastLogin: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toLocaleDateString()
}));

const Users = () => {
  const [users] = useState(mockUsers);
  const [filteredUsers, setFilteredUsers] = useState(mockUsers);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [error, setError] = useState('');

  // Filter users based on search
  const handleSearch = (value: string) => {
    setSearchTerm(value);
    const filtered = users.filter(user =>
      user.name.toLowerCase().includes(value.toLowerCase()) ||
      user.email.toLowerCase().includes(value.toLowerCase())
    );
    setFilteredUsers(filtered);
    setCurrentPage(1);
  };

  // Pagination
  const totalPages = Math.ceil(filteredUsers.length / pageSize);
  const startIndex = (currentPage - 1) * pageSize;
  const currentUsers = filteredUsers.slice(startIndex, startIndex + pageSize);

  // Form configuration
  const userFormFields: FormFieldConfig[] = [
    {
      name: 'name',
      label: 'Full Name',
      type: 'text',
      required: true,
      validation: (value) => value.length < 2 ? 'Name must be at least 2 characters' : undefined
    },
    {
      name: 'email',
      label: 'Email Address',
      type: 'email',
      required: true,
      validation: (value) =>
        /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? undefined : 'Please enter a valid email'
    },
    {
      name: 'role',
      label: 'Role',
      type: 'select',
      required: true,
      options: [
        { label: 'Admin', value: 'admin' },
        { label: 'User', value: 'user' },
        { label: 'Viewer', value: 'viewer' }
      ]
    },
    {
      name: 'permissions',
      label: 'Permissions',
      type: 'checkbox',
      options: [
        { label: 'Read Access', value: 'read' },
        { label: 'Write Access', value: 'write' },
        { label: 'Delete Access', value: 'delete' },
        { label: 'Admin Access', value: 'admin' }
      ]
    },
    {
      name: 'notes',
      label: 'Notes',
      type: 'textarea',
      helperText: 'Optional notes about this user'
    }
  ];

  const handleCreateUser = async (data: Record<string, any>) => {
    setError('');
    console.log('Creating user:', data);

    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 1000));

    if (Math.random() > 0.8) {
      setError('Failed to create user. Email might already exist.');
      throw new Error('Failed to create user');
    }

    setShowCreateForm(false);
    alert(`User ${data.name} created successfully!`);
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
      label: 'Reset Password',
      onClick: () => alert(`Resetting password for ${user.email}`)
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

  if (showCreateForm) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-redis-xl font-bold text-redis-dusk-01">Create New User</h1>
            <p className="text-redis-sm text-redis-dusk-04 mt-1">
              Add a new user to your application
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => setShowCreateForm(false)}
          >
            Back to Users
          </Button>
        </div>

        <Card>
          <CardContent>
            {error && (
              <div className="mb-6">
                <ErrorMessage message={error} title="Creation Error" />
              </div>
            )}
            <Form
              fields={userFormFields}
              onSubmit={handleCreateUser}
              onCancel={() => setShowCreateForm(false)}
              submitLabel="Create User"
              layout="horizontal"
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-redis-xl font-bold text-redis-dusk-01">Users</h1>
          <p className="text-redis-sm text-redis-dusk-04 mt-1">
            Manage users and their permissions
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => setShowCreateForm(true)}
        >
          Add User
        </Button>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <Input
                placeholder="Search users by name or email..."
                value={searchTerm}
                onChange={(e) => handleSearch(e.target.value)}
              />
            </div>
            <Button variant="outline">Export</Button>
            <Button variant="outline">Filter</Button>
          </div>
        </CardContent>
      </Card>

      {/* Users Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h3 className="text-redis-lg font-semibold text-redis-dusk-01">
              All Users ({filteredUsers.length})
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-redis-xs text-redis-dusk-04">
                Showing {startIndex + 1}-{Math.min(startIndex + pageSize, filteredUsers.length)} of {filteredUsers.length}
              </span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {/* Table Header */}
          <div className="grid grid-cols-12 gap-4 p-4 border-b border-redis-dusk-08 bg-redis-dusk-09">
            <div className="col-span-4 text-redis-xs font-medium text-redis-dusk-04">USER</div>
            <div className="col-span-2 text-redis-xs font-medium text-redis-dusk-04">ROLE</div>
            <div className="col-span-2 text-redis-xs font-medium text-redis-dusk-04">STATUS</div>
            <div className="col-span-3 text-redis-xs font-medium text-redis-dusk-04">LAST LOGIN</div>
            <div className="col-span-1 text-redis-xs font-medium text-redis-dusk-04">ACTIONS</div>
          </div>

          {/* Table Rows */}
          <div className="divide-y divide-redis-dusk-08">
            {currentUsers.map((user) => (
              <div key={user.id} className="grid grid-cols-12 gap-4 p-4 hover:bg-redis-dusk-09 transition-colors">
                <div className="col-span-4 flex items-center gap-3">
                  <Avatar fallback={user.name} size="sm" />
                  <div>
                    <p className="text-redis-sm font-medium text-redis-dusk-01">{user.name}</p>
                    <p className="text-redis-xs text-redis-dusk-04">{user.email}</p>
                  </div>
                </div>
                <div className="col-span-2 flex items-center">
                  <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                    user.role === 'Admin'
                      ? 'bg-redis-red/20 text-redis-red'
                      : user.role === 'User'
                      ? 'bg-redis-blue-03/20 text-redis-blue-03'
                      : 'bg-redis-dusk-07 text-redis-dusk-04'
                  }`}>
                    {user.role}
                  </span>
                </div>
                <div className="col-span-2 flex items-center">
                  <span className={`px-2 py-1 rounded-redis-xs text-redis-xs font-medium ${
                    user.status === 'Active'
                      ? 'bg-redis-green/20 text-redis-green'
                      : 'bg-redis-dusk-07 text-redis-dusk-04'
                  }`}>
                    {user.status}
                  </span>
                </div>
                <div className="col-span-3 flex items-center">
                  <span className="text-redis-sm text-redis-dusk-04">{user.lastLogin}</span>
                </div>
                <div className="col-span-1 flex items-center">
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
            ))}
          </div>
        </CardContent>

        {/* Pagination */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          itemCount={filteredUsers.length}
          itemLabel="users"
          pageSize={pageSize}
          pageSizeOptions={[5, 10, 25, 50]}
          onPageChange={setCurrentPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setCurrentPage(1);
          }}
        />
      </Card>
    </div>
  );
};

export default Users;
