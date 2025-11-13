# Radar UI Kit - Standalone Setup Guide

This guide covers setting up the Radar UI Kit as a standalone repository for independent development and distribution.

## 🚀 Quick Start

### 1. Move to Standalone Repository

```bash
# Create new repository
git init radar-ui-kit
cd radar-ui-kit

# Copy the ui-kit directory contents
cp -r /path/to/radar/ui-kit/* .

# Initialize package
npm install

# Build the library
npm run build

# Run tests
npm test

# Start Storybook for development
npm run storybook
```

### 2. Verify Independence

The library is completely self-contained with:
- ✅ All dependencies defined in package.json
- ✅ Complete build system (Vite + TypeScript)
- ✅ Testing setup (Vitest + React Testing Library)
- ✅ Linting and formatting (ESLint + Prettier)
- ✅ Storybook for component development
- ✅ Tailwind CSS with full Redis design system

## 📦 Publishing Setup

### 1. Update package.json

Before publishing, update these fields in `package.json`:

```json
{
  "name": "@your-org/ui-kit",
  "repository": "https://github.com/your-org/radar-ui-kit",
  "bugs": "https://github.com/your-org/radar-ui-kit/issues",
  "homepage": "https://github.com/your-org/radar-ui-kit#readme"
}
```

### 2. NPM Publishing

```bash
# Login to npm
npm login

# Publish to npm (or private registry)
npm publish

# Or for scoped packages
npm publish --access public
```

### 3. GitHub Actions (Optional)

Create `.github/workflows/publish.yml`:

```yaml
name: Publish Package

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          registry-url: 'https://registry.npmjs.org'
      - run: npm ci
      - run: npm run build
      - run: npm run test
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

## 🛠 Development Workflow

### Available Scripts

```bash
# Development
npm run dev          # Watch mode for library building
npm run storybook    # Component development and documentation

# Building
npm run build        # Build the library for distribution
npm run clean        # Remove dist folder

# Quality
npm run test         # Run tests
npm run test:watch   # Run tests in watch mode
npm run test:coverage # Generate coverage report
npm run lint         # Run ESLint
npm run lint:fix     # Fix ESLint issues
npm run format       # Format code with Prettier
npm run typecheck    # TypeScript type checking
```

### Adding New Components

1. **Create component directory**:
```bash
mkdir src/components/NewComponent
```

2. **Create component files**:
```bash
# Component implementation
touch src/components/NewComponent/NewComponent.tsx

# Tests
touch src/components/NewComponent/NewComponent.test.tsx

# Storybook stories
touch src/components/NewComponent/NewComponent.stories.tsx
```

3. **Export from main index**:
```typescript
// src/index.ts
export { NewComponent } from './components/NewComponent/NewComponent';
export type { NewComponentProps } from './components/NewComponent/NewComponent';
```

## 📚 Documentation

### Storybook

The library includes Storybook for component documentation:

```bash
# Development
npm run storybook

# Build static documentation
npm run build-storybook
```

### Component Documentation

Each component should include:
- TypeScript props interface
- Storybook stories with all variants
- Unit tests
- JSDoc comments for complex props

Example:
```tsx
/**
 * Primary button component with loading and variant support
 */
export interface ButtonProps {
  /** Button visual style */
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'destructive';
  /** Button size */
  size?: 'sm' | 'md' | 'lg';
  /** Shows loading spinner when true */
  isLoading?: boolean;
  /** Button content */
  children: React.ReactNode;
}
```

## 🎨 Design System Customization

### Extending the Theme

The design system is built with CSS custom properties. Override them:

```css
/* Your app's CSS */
:root {
  --color-redis-blue-03: #your-custom-blue;
  --radius-redis-sm: 8px;
}
```

### Adding New Design Tokens

1. **Add to CSS variables**:
```css
/* src/styles/index.css */
--color-redis-new-color: #123456;
```

2. **Use in components**:
```tsx
className="bg-redis-new-color text-white"
```

## 🔧 Integration Examples

### React App

```tsx
// main.tsx
import '@your-org/ui-kit/styles';

// Component usage
import { Button, Card, Input } from '@your-org/ui-kit';

function App() {
  return (
    <Card>
      <Input label="Email" />
      <Button variant="primary">Submit</Button>
    </Card>
  );
}
```

### Next.js App

```typescript
// next.config.js
module.exports = {
  transpilePackages: ['@your-org/ui-kit'],
};
```

```tsx
// _app.tsx
import '@your-org/ui-kit/styles';
```

### Vite App

```typescript
// vite.config.ts
export default defineConfig({
  optimizeDeps: {
    include: ['@your-org/ui-kit']
  }
});
```

## 🚨 Troubleshooting

### Build Issues

1. **TypeScript errors**: Run `npm run typecheck` to isolate type issues
2. **Dependency conflicts**: Check peer dependencies in consuming projects
3. **CSS not loading**: Ensure styles are imported in the consuming app

### Testing Issues

1. **Component tests failing**: Check test setup in `src/test/setup.ts`
2. **Missing DOM methods**: Ensure jsdom environment is configured in vitest

### Publishing Issues

1. **Private registry**: Configure `.npmrc` for private registries
2. **Scope permissions**: Ensure your npm account has access to the scope
3. **Build before publish**: The `prepublishOnly` script handles this automatically

## 📈 Maintenance

### Versioning

Follow semantic versioning:
- **Patch** (1.0.1): Bug fixes, no breaking changes
- **Minor** (1.1.0): New features, backward compatible
- **Major** (2.0.0): Breaking changes

### Dependency Updates

```bash
# Check for updates
npm outdated

# Update dependencies
npm update

# Test after updates
npm run test && npm run build
```

### Monitoring Usage

Track library usage in consuming applications:
- Bundle size impact
- Component adoption rates
- Performance metrics
- User feedback

This setup ensures your UI kit can operate completely independently while maintaining all the functionality and design consistency of the original Radar application.
