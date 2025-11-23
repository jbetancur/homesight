# HomeSight CI/CD Pipeline

Complete guide to HomeSight's automated build and release process.

## Overview

The CI/CD pipeline is implemented using GitHub Actions and automatically:

1. **Builds** binaries for multiple platforms (Linux amd64, arm64)
2. **Tests** the code with race condition detection
3. **Lints** the code for quality standards
4. **Builds Docker images** for the AI sidecar
5. **Pushes** artifacts to GitHub Container Registry (GHCR)
6. **Creates releases** with pre-built binaries

## Workflow Triggers

### On Every Push to `main` Branch
- Build binaries for all platforms
- Run tests and linting
- Build and push Docker images (tagged as `main`)
- Upload artifacts

### On Pull Requests to `main`
- Build binaries for all platforms
- Run tests and linting
- Verify Docker image builds

### On Release Tags (v*)
- Build binaries for all platforms
- Run tests and linting
- Build and push Docker images with version tags
- Create GitHub release with binary artifacts
- Upload binaries to GitHub release

## Files

### `.github/workflows/build.yml`

The main CI/CD workflow file with three jobs:

#### `build` Job
- **Runs on**: Ubuntu latest
- **Matrix**: Linux amd64, arm64
- **Steps**:
  - Checkout code
  - Set up Go 1.25
  - Build binary: `homesightd-linux-{arch}`
  - Upload as artifact
  - Upload to GitHub release (on tags)

#### `docker-build` Job
- **Runs on**: Ubuntu latest (only on main branch or tags)
- **Steps**:
  - Checkout code
  - Set up QEMU for ARM64 support
  - Set up Docker Buildx for multi-platform builds
  - Log in to GHCR with token
  - Extract metadata (version, tag, sha)
  - Build and push multi-platform Docker image

#### `test` Job
- **Runs on**: Ubuntu latest
- **Steps**:
  - Checkout code
  - Set up Go 1.25
  - Run tests with race detection: `go test -v -race ./...`
  - Run golangci-lint for code quality

## Binary Artifacts

### Naming Convention

Binaries follow the pattern: `homesightd-{os}-{arch}`

Example:
- `homesightd-linux-amd64` - Linux 64-bit Intel/AMD
- `homesightd-linux-arm64` - Linux ARM 64-bit (Raspberry Pi 4+, AWS Graviton, etc.)

### Where to Find

1. **GitHub Releases**: https://github.com/homesight/homesight/releases
   - Automatically created on version tags
   - Download pre-built binaries for your platform

2. **GitHub Actions Artifacts**:
   - Available for 90 days after build
   - Accessible from workflow runs

## Docker Images

### Registry

Images are pushed to GitHub Container Registry (GHCR):

```
ghcr.io/homesight/homesight:{tag}
```

### Tags

- `main` - Latest from main branch
- `v1.0.0` - Specific release version
- `latest` - Alias for latest release
- `sha-{commit-sha}` - Specific commit

### Usage

```bash
docker pull ghcr.io/homesight/homesight:latest
docker pull ghcr.io/homesight/homesight:v1.0.0
```

## Creating a Release

### Manual Release Process

1. **Ensure tests pass** on the main branch
2. **Tag the commit** with version:
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0"
   git push origin v1.0.0
   ```
3. **GitHub Actions automatically**:
   - Builds binaries for all platforms
   - Runs tests
   - Creates Docker image with version tag
   - Creates GitHub release with binaries attached

4. **Verify release**:
   - Check https://github.com/homesight/homesight/releases
   - Confirm binaries are present
   - Confirm Docker images are pushed to GHCR

## Installation from Release

### Using Release Binary (Recommended for Production)

```bash
sudo bash scripts/install-ubuntu-release.sh
```

This script:
- Downloads the latest binary from GitHub releases
- Sets up systemd services
- Configures everything for production use

### Version-Specific Installation

```bash
HOMESIGHT_VERSION=v1.0.0 sudo bash scripts/install-ubuntu-release.sh
```

### Using Docker Image

```bash
docker-compose up -d
```

## Development Setup

For development, use the source build:

```bash
bash scripts/install-ubuntu.sh
```

This will:
- Install Go 1.25
- Set up Docker
- Clone the repository
- Allow local builds and testing

## Local Build (Development)

```bash
# Build binary
go build -o ./bin/homesightd ./cmd/homesightd

# Run tests
go test -v -race ./...

# Build Docker image
docker build -f docker/ai-sidecar/Dockerfile -t homesight:dev .

# Run
./bin/homesightd
```

## Troubleshooting CI/CD

### Release Artifacts Not Showing

1. Check workflow runs: https://github.com/homesight/homesight/actions
2. Verify tag format matches `v*` pattern
3. Check for workflow failures in logs

### Docker Image Not Pushed

1. Verify GitHub token has `packages:write` permission
2. Check workflow logs for authentication errors
3. Ensure workflow runs on main branch or tagged commit

### Binary Download Fails

```bash
# Check if release exists
curl -s https://api.github.com/repos/homesight/homesight/releases/latest | jq '.tag_name'

# Download specific version
HOMESIGHT_VERSION=v1.0.0 sudo bash scripts/install-ubuntu-release.sh
```

## GitHub Container Registry Access

To use private images (if repository becomes private):

```bash
# Log in to GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull image
docker pull ghcr.io/homesight/homesight:latest
```

## Performance Notes

- Build jobs typically complete in 2-3 minutes
- Docker image build (multi-platform) may take 5-10 minutes
- Test suite runs in parallel

## Environment Variables Used in CI

- `GITHUB_TOKEN` - Automatically provided by GitHub Actions
- `GITHUB_REPOSITORY` - Owner/repo (e.g., `homesight/homesight`)
- `GOOS` - Set to `linux` for OS target
- `GOARCH` - Set to `amd64` or `arm64` for architecture

## Related Documentation

- [Installation Guide](INSTALL.md)
- [Quick Start Guide](QUICKSTART.md)
- [Release Process](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
