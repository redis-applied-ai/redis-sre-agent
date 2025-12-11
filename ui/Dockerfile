# Multi-stage Dockerfile for Redis SRE Agent UI
FROM node:20-alpine AS base

# Set working directory
WORKDIR /app

# Install dependencies for development
FROM base AS development

# Copy package files for both main app and ui-kit
COPY package*.json ./
COPY ui-kit/package*.json ./ui-kit/

# Copy ui-kit source (needed for build)
COPY ui-kit ./ui-kit/

# Install all dependencies (including dev dependencies)
# Use --ignore-scripts to skip pre-commit hooks that require Python
RUN npm ci --ignore-scripts

# Manually build ui-kit since we skipped scripts
RUN cd ui-kit && npm run build && cd ..

# Copy remaining source code
COPY . .

# Expose port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# Production build stage
FROM base AS build

# Copy package files for both main app and ui-kit
COPY package*.json ./
COPY ui-kit/package*.json ./ui-kit/

# Copy ui-kit source (needed for build)
COPY ui-kit ./ui-kit/

# Install dependencies
# Use --ignore-scripts to skip pre-commit hooks that require Python
RUN npm ci --ignore-scripts

# Manually build ui-kit since we skipped scripts
RUN cd ui-kit && npm run build && cd ..

# Copy remaining source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine AS production

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
