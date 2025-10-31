# @radar/ui-kit

A comprehensive UI component library with Redis-themed design system, extracted from the Radar monitoring application.

## Features

- **Complete Design System**: Redis-themed colors, typography, spacing, and utilities
- **17 React Components**: From basic buttons to complex forms and layouts
- **TypeScript First**: Full type safety and IntelliSense support
- **Tailwind CSS**: Utility-first styling with custom Redis theme
- **Tree Shakable**: Only import the components you need
- **Storybook Ready**: Component documentation and development
- **Testing Included**: Unit tests and setup for component testing

## Quick Start

### Try the Example App

See all components in action with the included example app:

```bash
# Install dependencies for the main UI Kit
npm install

# Build the UI Kit library
npm run build

# Install dependencies for the example app
cd example
npm install

# Start the example app
npm run dev
```

**Note**: If you get dependency errors, make sure to install dependencies in both the root directory and the example directory, and ensure the UI Kit is built first.

Open [http://localhost:5173](http://localhost:5173) to explore all components and features. The example app demonstrates notifications (opaque toasts, inline alerts, banners), high‑contrast status badges, deployments with working overflow menus, and compact pagination.

### Create a New App

Use the built-in script to scaffold a new application:

```bash
# Create a new app with the UI Kit
./scripts/create-app.sh my-app /path/to/my-app

# Navigate and start developing
cd /path/to/my-app
npm run dev
```

## Installation

```bash
npm install @radar/ui-kit
```

## Usage

### Basic Setup

Import the CSS file in your app entry point:

```tsx
// main.tsx or App.tsx
import '@radar/ui-kit/styles';
```

Then use components in your application:

```tsx
import { Button, Card, Input, Header, Layout } from '@radar/ui-kit';

function MyApp() {
  return (
    <Layout
      header={
        <Header
          logo={<div>My App</div>}
          navigationItems={[
            { label: 'Home', href: '/' },
            { label: 'About', href: '/about' }
          ]}
        />
      }
    >
      <Card>
        <Input label="Email" type="email" />
        <Button variant="primary">Submit</Button>
      </Card>
    </Layout>
  );
}
```

## Component Categories

### 🧱 Core Components (7)
- **Button** - 5 variants, loading states, multiple sizes
- **Input** - Labels, validation, helper text
- **Card** - Base card with header/content/footer variants
- **Tooltip** - Smart positioning with multiple placements
- **Loader** - Spinning loader with size variants
- **ErrorMessage** - Full and compact error display variants
- **Avatar** - User avatars with fallbacks and sizes

### 🏗 Layout Components (2)
- **Header** - Flexible header with navigation and user content
- **Layout** - Main layout wrapper with header, sidebar, footer support

### 🧭 Navigation Components (3)
- **Pagination** - Full-featured pagination with page size controls (compact sizing and improved spacing)
- **DropdownMenu** - Flexible dropdown with icons and actions (renders in a portal, closes on outside click and Escape)
- **CollapsibleCard** - Expandable card sections

### 📝 Form Components (2)
- **Form** - Complete form with validation and field management
- **FormField** - Individual form fields (text, select, checkbox, textarea)

### 🎨 Icons (7)
- Chevron icons (left, right, up, down, double variants)
- Copy icon for clipboard operations

## Component Examples

### Layout & Header
```tsx
import { Layout, Header, Avatar, DropdownMenu } from '@radar/ui-kit';

const userMenuItems = [
  { label: 'Profile', href: '/profile', icon: <UserIcon /> },
  { label: 'Settings', href: '/settings' },
  { label: 'Logout', onClick: handleLogout, variant: 'destructive' }
];

<Layout
  header={
    <Header
      logo={<Logo />}
      navigationItems={[
        { label: 'Dashboard', href: '/', isActive: true },
        { label: 'Analytics', href: '/analytics' }
      ]}
      userEmail="user@example.com"
      rightContent={
        <DropdownMenu 
          trigger={<Avatar size="sm" />}
          items={userMenuItems}
        />
      }
    />
  }
>
  <YourAppContent />
</Layout>
```

### Forms
```tsx
import { Form, Card } from '@radar/ui-kit';

const userFormFields = [
  {
    name: 'email',
    label: 'Email Address',
    type: 'email',
    required: true,
    validation: (value) => 
      /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value) ? undefined : 'Invalid email'
  },
  {
    name: 'role',
    label: 'User Role',
    type: 'select',
    required: true,
    options: [
      { label: 'Admin', value: 'admin' },
      { label: 'User', value: 'user' }
    ]
  },
  {
    name: 'permissions',
    label: 'Permissions',
    type: 'checkbox',
    options: [
      { label: 'Read', value: 'read' },
      { label: 'Write', value: 'write' },
      { label: 'Delete', value: 'delete' }
    ]
  }
];

<Card>
  <Form
    title="Create User"
    fields={userFormFields}
    onSubmit={handleSubmit}
    onCancel={handleCancel}
    submitLabel="Create User"
  />
</Card>
```

### Pagination
```tsx
import { Pagination } from '@radar/ui-kit';

<Pagination
  currentPage={currentPage}
  totalPages={totalPages}
  itemCount={filteredItems.length}
  itemLabel="deployments"
  pageSize={pageSize}
  pageSizeOptions={[10, 25, 50, 100]}
  onPageChange={setCurrentPage}
  onPageSizeChange={setPageSize}
/>
```

### Advanced Components
```tsx
import { CollapsibleCard, Tooltip } from '@radar/ui-kit';

const configSections = [
  {
    id: 'agent',
    title: 'Agent Configuration',
    icon: <ServerIcon />,
    content: <AgentConfigForm />
  },
  {
    id: 'credentials',
    title: 'Redis Credentials',
    icon: <KeyIcon />,
    content: <CredentialsForm />
  }
];

<CollapsibleCard
  title="Deployment Configuration"
  description="Configure your Redis deployment settings"
  sections={configSections}
  defaultExpandedSection="agent"
/>

<Tooltip content="Click to copy API key" placement="top">
  <Button variant="ghost" size="sm">
    <CopyIcon />
  </Button>
</Tooltip>
```

## Design System

### Colors
```css
/* Dark Theme (Primary) */
--color-redis-midnight: #091a23;    /* Dark backgrounds */
--color-redis-dusk-09: #0d212c;     /* Card backgrounds */
--color-redis-dusk-01: #f3f3f3;     /* Light text */

/* Accent Colors */
--color-redis-blue-03: #405bff;     /* Primary blue */
--color-redis-red: #ff4438;         /* Error/destructive */
--color-redis-green: #3cde67;       /* Success */
```

### Typography
```css
--text-redis-xs: 12px;      /* Small text */
--text-redis-sm: 14px;      /* Body text */
--text-redis-base: 16px;    /* Default */
--text-redis-lg: 20px;      /* Headings */
--text-redis-xl: 24px;      /* Large headings */
```

### Utility Classes
```css
.redis-button-base  /* Button foundation */
.redis-input-base   /* Input field foundation */  
.redis-card-base    /* Card foundation */
/* High-contrast badge helpers */
.badge .badge-success .badge-warning .badge-critical .badge-info .badge-neutral
```

## Customization

### Override Theme Colors
```css
:root {
  --color-redis-blue-03: #your-primary-color;
  --color-redis-midnight: #your-background;
}
```

### Extend Components
```tsx
const CustomButton = ({ className, ...props }) => (
  <Button 
    className={cn('my-custom-styles', className)}
    {...props}
  />
);
```

## Development

### Building
```bash
npm run build          # Build for production
npm run dev           # Development watch mode
```

### Testing
```bash
npm run test          # Run unit tests
npm run test:watch    # Watch mode
npm run test:coverage # Coverage report
```

### Storybook
```bash
npm run storybook           # Start Storybook
npm run build-storybook     # Build static docs
```

### Code Quality
```bash
npm run lint          # Run ESLint
npm run format        # Format with Prettier
npm run typecheck     # TypeScript checking
```

## Integration Examples

### Next.js
```typescript
// next.config.js
module.exports = {
  transpilePackages: ['@radar/ui-kit'],
};

// _app.tsx
import '@radar/ui-kit/styles';
```

### Vite
```typescript
// vite.config.ts
export default defineConfig({
  optimizeDeps: {
    include: ['@radar/ui-kit']
  }
});
```

## Contributing

1. Follow existing component patterns and TypeScript types
2. Add Storybook stories for new components
3. Include unit tests for functionality
4. Update documentation for new features
5. Ensure components follow Redis design system

## Troubleshooting

### Common Issues

**"react-router-dom could not be resolved" in example app:**
1. Make sure you've installed dependencies in both directories:
   ```bash
   npm install           # Install root dependencies
   cd example && npm install  # Install example dependencies
   ```
2. Ensure the UI Kit is built first: `npm run build`

**Build errors about missing CSS:**
- Run `npm run build` in the root directory to generate the CSS file
- Make sure you're importing styles correctly: `import '@radar/ui-kit/styles'`

**Pre-commit hooks not working:**
```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

**Development setup issues:**
Use the setup script to install everything at once:
```bash
./scripts/setup-dev.sh
```

## License

MIT - see main project license
