# Multi-stage Dockerfile for Redis SRE Agent UI
FROM node:20-alpine AS base

# Set working directory
WORKDIR /app

# Install dependencies for development
FROM base AS development

# Copy package files for both main app and ui-kit
COPY package*.json ./
COPY ui-kit/package*.json ./ui-kit/

# Install root dependencies, skipping postinstall (we'll build ui-kit after copying source)
RUN npm ci --ignore-scripts

# Install ui-kit dependencies
RUN npm --prefix ./ui-kit ci --ignore-scripts

# Copy remaining source code
COPY . .

# Build ui-kit now that source files are present
RUN npm --prefix ./ui-kit run build

# Expose port
EXPOSE 3000

# Start development server
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]

# Production build stage
FROM base AS build

# Copy package files for both main app and ui-kit
COPY package*.json ./
COPY ui-kit/package*.json ./ui-kit/

# Install root dependencies, skipping postinstall
RUN npm ci --ignore-scripts

# Install ui-kit dependencies
RUN npm --prefix ./ui-kit ci --ignore-scripts

# Copy remaining source code
COPY . .

# Build ui-kit first, then the main app
RUN npm --prefix ./ui-kit run build && npm run build

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
