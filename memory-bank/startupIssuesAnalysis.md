# Startup Issues Analysis - Polly Discord Bot

## Current Task Status: FIXING STARTUP ISSUES 🔧
**Date**: 2025-09-19
**Priority**: HIGH - Application won't start

## Issues Identified

### 1. Permission Denied Errors ❌
```
mkdir: cannot create directory 'static/uploads': Permission denied
mkdir: cannot create directory 'static/avatars': Permission denied
mkdir: cannot create directory 'static/images': Permission denied
mkdir: cannot create directory 'static/polls': Permission denied
```

**Root Cause**: 
- [`docker-entrypoint.sh:8`](docker-entrypoint.sh:8) tries to create directories after switching to non-root user
- Dockerfile switches to `polly` user at line 32, but directories are created at runtime
- Non-root user lacks permission to create directories in `/app`

### 2. Scalene Build Failure ❌
```
× Failed to build `scalene==1.5.54`
error: command 'make' failed: No such file or directory
```

**Root Cause**:
- [`pyproject.toml:50`](pyproject.toml:50) includes `scalene>=1.5.54` in dev-dependencies
- Scalene requires `make` command which is not available in `python:3.13-slim` base image
- Build system missing essential build tools for native extensions

### 3. Deprecated Configuration Warning ⚠️
```
warning: The `tool.uv.dev-dependencies` field (used in `pyproject.toml`) is deprecated 
and will be removed in a future release; use `dependency-groups.dev` instead
```

**Root Cause**:
- [`pyproject.toml:38-51`](pyproject.toml:38) uses deprecated `[tool.uv]` configuration
- Should use modern `dependency-groups.dev` format

## Impact Assessment

### Severity: CRITICAL
- **Application cannot start** due to permission errors
- **Development environment broken** due to scalene build failure
- **Deployment blocked** - container fails during startup

### Affected Components:
1. **Static File Handling** - No uploads/avatars/images directories
2. **Development Tooling** - Memory profiling tools unavailable
3. **CI/CD Pipeline** - Builds fail due to dependency issues

## Solution Strategy

### 1. Dockerfile Permission Fix
- Create static directories **before** switching to non-root user
- Ensure proper ownership of directories
- Remove directory creation from docker-entrypoint.sh

### 2. Remove Problematic Dependencies
- Remove `scalene` from dev-dependencies (requires build tools)
- Keep essential memory monitoring tools: `memray`, `pytest-memray`
- Document alternative memory profiling approaches

### 3. Modernize Configuration
- Update `pyproject.toml` to use `dependency-groups.dev`
- Remove deprecated `[tool.uv]` section
- Ensure compatibility with latest uv version

## Technical Context

### Current Docker Setup:
```dockerfile
FROM python:3.13-slim          # Minimal base image
RUN adduser --uid 1000 polly   # Create non-root user
USER polly                     # Switch to non-root user
CMD ["./docker-entrypoint.sh"] # Run entrypoint script
```

### Directory Creation Issue:
```bash
# This fails because polly user can't create directories in /app
mkdir -p static/uploads static/avatars static/images static/polls
```

### Memory Optimization Context:
- Previous memory optimization work is **COMPLETE** ✅
- Core memory utilities implemented without scalene dependency
- Advanced monitoring available via `psutil` and `memray`

## Risk Mitigation

### Zero-Downtime Fix:
1. **Backward Compatible**: All fixes maintain existing functionality
2. **Gradual Deployment**: Can test changes in development first
3. **Rollback Ready**: Changes are minimal and reversible

### Alternative Memory Profiling:
- **memray**: Available and working for detailed memory analysis
- **psutil**: Built-in system monitoring capabilities
- **pytest-memray**: Memory regression testing in CI/CD

## Next Steps Priority Order

1. **Fix Directory Permissions** (Dockerfile)
2. **Remove Scalene Dependency** (pyproject.toml)
3. **Modernize Configuration** (pyproject.toml)
4. **Update Entrypoint Script** (docker-entrypoint.sh)
5. **Test Complete Startup** (verification)

The startup issues are **blocking deployment** but have **clear solutions** that maintain all existing functionality while fixing the core problems.