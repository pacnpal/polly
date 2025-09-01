# Docker Configuration Updates

## Changes Made for Database Migration Support

### 1. Updated Dockerfile ✅

**Changes:**
- Added `migrate_database.py` to the copied files
- Created additional directories: `logs` and `data`
- Added `docker-entrypoint.sh` script
- Changed CMD to use the entrypoint script instead of directly running the app

**New Features:**
- Automatic database migration on container startup
- Proper directory structure for logs and data persistence

### 2. Created docker-entrypoint.sh ✅

**Purpose:** 
- Sets up proper directory permissions
- Runs database migration before starting the application
- Ensures database schema is always up-to-date on container startup

**Process:**
1. Creates and sets permissions for `static/uploads`, `logs`, and `data` directories
2. Ensures proper ownership for write access
3. Runs `migrate_database.py` to update database schema
4. Starts the main application with `polly.main`

### 3. Updated docker-compose.yml ✅

**Changes:**
- Added `env_file: - .env` to automatically load environment variables
- Added `./logs:/app/logs` volume mapping for log persistence
- Added `polly_db:/app` named volume for database persistence
- Updated nginx volume mappings to use proper directory structure
- Added `volumes:` section to define the named volume

**Benefits:**
- Automatic .env file loading for environment variables
- Database persists between container restarts
- Logs are accessible from the host system
- Uploaded images persist in `./static/uploads`
- Proper nginx configuration structure

### 4. Restructured Nginx Configuration ✅

**Changes:**
- Created `nginx/` directory with proper structure
- Moved site config to `nginx/sites-available/polly.conf`
- Created proper main `nginx/nginx.conf`
- Added `nginx/sites-enabled/` with symlink structure
- Updated docker-compose.yml to use new nginx structure

**Benefits:**
- Follows nginx best practices
- Easier to manage multiple sites
- Proper separation of main config and site configs
- Standard nginx directory structure

## How It Works

### Container Startup Process:
1. **Build Phase**: Dockerfile copies all necessary files including migration script
2. **Startup Phase**: `docker-entrypoint.sh` runs database migration
3. **Migration Phase**: `migrate_database.py` updates database schema if needed
4. **Application Phase**: Main application starts with restored scheduled jobs

### Volume Mapping:
- `./data:/app/data` - Application data persistence
- `./static/uploads:/app/static/uploads` - Uploaded poll images
- `./logs:/app/logs` - Application logs
- `polly_db:/app` - Database files (named volume)

## Deployment Commands

### First Time Setup:
```bash
# Build and start containers
docker-compose up --build -d

# Check logs
docker-compose logs -f polly
```

### Updates/Restarts:
```bash
# Rebuild and restart (migration runs automatically)
docker-compose up --build -d

# Or just restart existing containers
docker-compose restart
```

### Database Migration:
- **Automatic**: Runs on every container startup
- **Manual**: `docker-compose exec polly uv run python migrate_database.py`

## Benefits of These Updates

1. **Zero-Downtime Migrations**: Database schema updates automatically on deployment
2. **Data Persistence**: Database and uploads survive container restarts
3. **Log Access**: Easy access to application logs from host system
4. **Scheduled Job Recovery**: Jobs are restored from database on startup
5. **Simplified Deployment**: Single `docker-compose up` command handles everything

## Backward Compatibility

- Existing databases will be automatically migrated
- No manual intervention required for schema updates
- All existing functionality preserved
- New installations work out of the box

The Docker configuration now fully supports the poll scheduling fixes and database migration system.
