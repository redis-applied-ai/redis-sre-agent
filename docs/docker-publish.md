# Publishing Docker Images

This document describes how to publish Docker images to Docker Hub.

## Prerequisites

### 1. Docker Hub Access Token

You need to create a Docker Hub access token and add it as a GitHub secret.

**Steps to create the token:**

1. Go to https://hub.docker.com/settings/security
2. Click "New Access Token"
3. Name: `github-actions-redis-sre-agent`
4. Access permissions: `Read, Write, Delete`
5. Click "Generate"
6. **Copy the token immediately** (you won't be able to see it again)

### 2. Add GitHub Secret

Add the Docker Hub token as a GitHub repository secret:

1. Go to https://github.com/redis-applied-ai/redis-sre-agent/settings/secrets/actions
2. Click "New repository secret"
3. Name: `DOCKERHUB_TOKEN`
4. Value: Paste the Docker Hub access token
5. Click "Add secret"

## Publishing an Image

### Manual Publish via GitHub Actions

1. Go to https://github.com/redis-applied-ai/redis-sre-agent/actions/workflows/publish-docker.yml
2. Click "Run workflow"
3. Select the branch (usually `main`)
4. Enter the tag (e.g., `v1.0.0`, `latest`, `dev`)
5. Optionally check "Also tag as latest" to push both the specified tag and `latest`
6. Click "Run workflow"

The workflow will:
- Build the Docker image for both `linux/amd64` and `linux/arm64`
- Push to `abrookins/redis-sre-agent` on Docker Hub
- Tag with the specified version
- Optionally also tag as `latest`
- Use build cache to speed up subsequent builds

### Image Tags

The published image will be available at:
```
docker pull abrookins/redis-sre-agent:<tag>
```

Examples:
```bash
# Pull specific version
docker pull abrookins/redis-sre-agent:v1.0.0

# Pull latest
docker pull abrookins/redis-sre-agent:latest

# Pull branch-specific build
docker pull abrookins/redis-sre-agent:main-abc1234
```

## Using the Published Image

Update your `docker-compose.yml` to use the published image instead of building locally:

```yaml
services:
  sre-agent:
    image: abrookins/redis-sre-agent:latest
    # Remove the 'build' section
    ports:
      - "8000:8000"
    # ... rest of config
```

## Versioning Strategy

Recommended tagging strategy:

- `latest` - Latest stable release
- `v1.0.0` - Semantic version tags for releases
- `dev` - Development/unstable builds
- `main-<sha>` - Automatic tags from main branch commits

## Troubleshooting

### Authentication Failed

If you see authentication errors:
1. Verify the `DOCKERHUB_TOKEN` secret is set correctly
2. Check that the token hasn't expired
3. Ensure the token has `Read, Write, Delete` permissions

### Build Failed

If the build fails:
1. Check the GitHub Actions logs for specific errors
2. Verify the Dockerfile builds locally: `docker build -t test .`
3. Check that all dependencies are available

### Multi-platform Build Issues

If ARM64 builds fail:
- The workflow uses Docker Buildx for multi-platform builds
- Some dependencies may not be available for ARM64
- You can remove `linux/arm64` from the `platforms` list if needed
