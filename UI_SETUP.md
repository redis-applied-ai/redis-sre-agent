# Redis SRE Agent UI Setup

## Overview

The Redis SRE Agent UI is a React + Vite application that provides a web interface for interacting with the Redis SRE Agent. It's now fully integrated into the Docker Compose setup for easy development and deployment.

## Quick Start

### Development Mode

```bash
# Start all services including UI
docker-compose up -d

# Or start just the UI service
docker-compose up -d sre-ui

# Access the UI
open http://localhost:3002
```

### Production Mode

```bash
# Build and start in production mode
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Access the UI (served by nginx)
open http://localhost:3002
```

## Service Configuration

### Development Configuration

- **Framework**: React + Vite
- **Port**: 3000
- **Hot Reload**: Enabled with volume mounting
- **API Proxy**: Configured to proxy `/api`, `/health`, `/metrics` to backend
- **Environment**: `NODE_ENV=development`

### Production Configuration

- **Build**: Multi-stage Docker build with nginx
- **Port**: 80 (mapped to 3000 on host)
- **Serving**: Static files served by nginx
- **API Proxy**: nginx proxies API requests to backend
- **Optimization**: Gzip compression, caching headers, security headers

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Browser       │    │   UI Container  │    │  API Container  │
│   localhost:3000│◄──►│   sre-ui        │◄──►│   sre-agent     │
│                 │    │   (React/Vite)  │    │   (FastAPI)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Development Flow
1. **Browser** → **Vite Dev Server** (port 3000)
2. **Vite Proxy** → **API Container** (port 8000)
3. **Hot Reload** via volume mounting

### Production Flow
1. **Browser** → **nginx** (port 80)
2. **nginx** serves static files or proxies API requests
3. **API Proxy** → **API Container** (port 8000)

## Files Added/Modified

### New Files
- `ui/Dockerfile` - Multi-stage build for development and production
- `ui/nginx.conf` - nginx configuration for production
- `ui/.dockerignore` - Optimize Docker build context
- `docker-compose.prod.yml` - Production overrides

### Modified Files
- `docker-compose.yml` - Added `sre-ui` service
- `ui/vite.config.ts` - Added Docker-compatible configuration

## Environment Variables

### Development
- `NODE_ENV=development`
- `VITE_API_URL=http://sre-agent:8000` (internal Docker network)

### Production
- `NODE_ENV=production`
- API requests proxied by nginx

## Networking

The UI service is connected to the `sre-network` Docker network and can communicate with:

- **sre-agent**: API backend
- **redis**: Direct Redis access (if needed)
- **prometheus**: Metrics (if needed)
- **grafana**: Dashboards (if needed)

## Development Workflow

### Local Development
```bash
# Start all services
docker-compose up -d

# View UI logs
docker logs -f redis-sre-agent-sre-ui-1

# Rebuild UI after changes
docker-compose build sre-ui
docker-compose up -d sre-ui
```

### Hot Reload
The development setup includes volume mounting for hot reload:
```yaml
volumes:
  - ./ui:/app
  - /app/node_modules  # Anonymous volume for node_modules
```

Changes to files in `ui/src/` will automatically reload in the browser.

## Production Deployment

### Build Production Image
```bash
# Build production image
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build sre-ui

# Start production stack
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Production Features
- **Static file serving** with nginx
- **Gzip compression** for better performance
- **Caching headers** for static assets
- **Security headers** (XSS protection, frame options, etc.)
- **Client-side routing** support for React Router

## Troubleshooting

### UI Won't Start
```bash
# Check container logs
docker logs redis-sre-agent-sre-ui-1

# Check if port is available
lsof -i :3000

# Rebuild container
docker-compose build sre-ui
```

### API Requests Failing
```bash
# Check if API is running
curl http://localhost:8000/health

# Check network connectivity
docker exec redis-sre-agent-sre-ui-1 ping sre-agent

# Check proxy configuration
docker exec redis-sre-agent-sre-ui-1 cat /app/vite.config.ts
```

### Hot Reload Not Working
```bash
# Check volume mounting
docker inspect redis-sre-agent-sre-ui-1 | grep -A 10 Mounts

# Restart with fresh build
docker-compose down sre-ui
docker-compose up -d sre-ui
```

## Testing the Setup

### 1. Verify UI is Running
```bash
curl http://localhost:3000
# Should return HTML content
```

### 2. Test API Proxy
```bash
curl http://localhost:3000/health
# Should return API health status
```

### 3. Test in Browser
1. Open http://localhost:3000
2. Verify UI loads correctly
3. Test API interactions
4. Check browser console for errors

## Integration with SRE Agent

The UI integrates with the Redis SRE Agent API to provide:

- **Health monitoring** via `/health` endpoint
- **Knowledge search** via `/api/v1/search`
- **Agent queries** via `/api/v1/agent/query`
- **Task management** via `/api/v1/tasks`
- **Instance monitoring** via `/api/v1/instances`

All API requests are automatically proxied through the UI service to the backend API.

## Next Steps

1. **Start the UI service**: `docker-compose up -d sre-ui`
2. **Access the interface**: http://localhost:3000
3. **Test functionality**: Verify UI can communicate with the API
4. **Develop features**: Use hot reload for rapid development
5. **Deploy to production**: Use production docker-compose for deployment
