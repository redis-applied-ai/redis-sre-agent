# Redis SRE Agent - Web UI

A modern React-based web interface for the Redis SRE Agent, built with @radar/ui-kit and Vite.

## Features

- **Interactive Chat Interface**: Real-time conversations with the SRE agent
- **Session Management**: Persistent conversation sessions
- **Tool Execution Visualization**: See agent tool calls and results
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Updates**: Live updates during agent processing

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

Open http://localhost:5173

## Development

### Prerequisites

- Node.js 18+
- npm or yarn
- Redis SRE Agent API running on http://localhost:8000

### Project Structure

```
ui/
├── src/
│   ├── components/     # React components
│   ├── hooks/         # Custom React hooks
│   ├── services/      # API service layer
│   ├── types/         # TypeScript type definitions
│   ├── utils/         # Utility functions
│   └── App.tsx        # Main application component
├── public/            # Static assets
├── index.html         # HTML template
├── package.json       # Dependencies and scripts
├── tailwind.config.js # Tailwind CSS configuration
├── tsconfig.json      # TypeScript configuration
└── vite.config.ts     # Vite build configuration
```

### Available Scripts

- `npm run dev` - Start development server with hot reload
- `npm run build` - Build for production
- `npm run preview` - Preview production build locally
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript type checking

### API Integration

The UI connects to the Redis SRE Agent API at `http://localhost:8000` by default. Key endpoints:

- `POST /api/v1/agent/query` - Send queries to the agent
- `POST /api/v1/agent/chat` - Continue conversations
- `GET /api/v1/agent/sessions/{id}/history` - Get conversation history
- `GET /api/v1/health` - Check API health

### Styling

Uses Tailwind CSS for styling with the @radar/ui-kit component library for consistent design patterns.

### State Management

Uses React hooks and context for state management. No external state management library required for the current scope.

## Deployment

### Production Build

```bash
npm run build
```

The build artifacts will be in the `dist/` directory.

### Docker Deployment

The UI can be served using any static file server. For Docker deployment:

```dockerfile
FROM nginx:alpine
COPY dist/ /usr/share/nginx/html/
EXPOSE 80
```

### Environment Configuration

Configure the API endpoint via environment variables:

```bash
VITE_API_BASE_URL=http://localhost:8000
```

## Contributing

1. Follow the existing code style and patterns
2. Use TypeScript for type safety
3. Write responsive components using Tailwind CSS
4. Test components manually with the SRE agent API
5. Ensure accessibility standards are met
