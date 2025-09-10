# Polly DEBUG Mode Integration

This document describes the comprehensive DEBUG mode toggle system implemented for the Polly Discord poll bot. The system provides unified debugging control across both backend Python logging and frontend JavaScript console logging.

## Overview

The DEBUG mode system allows you to enable/disable verbose logging throughout the entire application with a single environment variable. When enabled, it provides detailed insights into application behavior for debugging and development purposes.

## Architecture

### 1. Centralized Configuration (`polly/debug_config.py`)

The core of the system is the `DebugConfig` class that:
- Reads the `DEBUG` environment variable (defaults to `False`)
- Manages logging levels for all Python modules
- Provides template context for frontend integration
- Supports programmatic runtime toggling

### 2. Backend Integration

**Updated Modules:**
- `polly/main.py` - Application entry point
- `polly/web_app.py` - FastAPI app and template context
- `polly/discord_utils.py` - Discord bot utilities
- `polly/htmx_endpoints.py` - HTMX endpoint handlers

**Key Changes:**
```python
# Old logging approach
import logging
logger = logging.getLogger(__name__)

# New debug-aware approach
from .debug_config import get_debug_logger
logger = get_debug_logger(__name__)
```

### 3. Frontend Integration

**JavaScript Debug Utilities (`static/polly-debug.js`):**
- `PollyDebug` global object with styled console logging
- Automatic HTMX event logging when debug mode is enabled
- Categorized logging methods (debug, info, warn, error, success, htmx, api, user, poll)
- Utility methods (group, table, time) for structured debugging

**Template Integration:**
- `POLLY_DEBUG` JavaScript variable injected into templates
- Debug script only loads when debug mode is active
- Consistent styling and timestamps for all debug output

## Configuration

### Environment Variable

Add to your `.env` file:
```bash
# Enable debug mode
DEBUG=true

# Disable debug mode (default)
DEBUG=false
```

### Effects of DEBUG Mode

#### When DEBUG=true:
**Backend:**
- Log level set to `DEBUG` (10)
- All `logger.debug()` calls will be visible
- More verbose output in `logs/polly.log` and console
- Detailed database, Discord API, and HTMX operation logging

**Frontend:**
- `POLLY_DEBUG = true` in JavaScript
- `PollyDebug.*` methods output styled messages to browser console
- Automatic HTMX request/response logging
- Visual debug mode indicator in console on page load

#### When DEBUG=false:
**Backend:**
- Log level set to `INFO` (20)
- Only INFO, WARNING, and ERROR messages visible
- Cleaner, production-ready logging output

**Frontend:**
- `POLLY_DEBUG = false` in JavaScript
- `PollyDebug.*` methods are silenced (no console output)
- No automatic HTMX logging
- No debug overhead in browser console

## Usage Examples

### Backend Logging

```python
from polly.debug_config import get_debug_logger

logger = get_debug_logger(__name__)

# This will only appear when DEBUG=true
logger.debug("🐛 Detailed debugging information")

# These always appear (when appropriate log level)
logger.info("ℹ️ Application started")
logger.warning("⚠️ Rate limit approaching")
logger.error("❌ Database connection failed")
```

### Frontend Logging

**In HTML templates (already integrated):**
```html
<!-- Debug context is automatically available -->
<script>
    const POLLY_DEBUG = {{ POLLY_DEBUG|lower }};
</script>
<script src="/static/polly-debug.js"></script>
```

**In JavaScript code:**
```javascript
// Styled debug logging (only shows when DEBUG=true)
PollyDebug.debug("Processing poll data", pollData);
PollyDebug.htmx("HTMX request starting", { url: "/api/polls" });
PollyDebug.user("User selected option", { option: 2, pollId: 123 });
PollyDebug.error("Validation failed", errorData);

// Utility methods
const timer = PollyDebug.time("Poll Creation");
// ... do work ...
timer.end();

const group = PollyDebug.group("HTMX Response Processing");
PollyDebug.debug("Response received");
PollyDebug.debug("Parsing data");
group.end();

PollyDebug.table(pollResults, "Poll Results Summary");
```

### Programmatic Control

```python
from polly.debug_config import get_debug_config

config = get_debug_config()

# Check current state
if config.debug_mode:
    print("Debug logging is active")

# Toggle programmatically (runtime only)
config.set_debug_mode(True)   # Enable debug logging
config.set_debug_mode(False)  # Disable debug logging
```

## Integration with Existing Code

### Template Updates

The main dashboard template (`templates/dashboard_htmx.html`) has been updated to include:

```html
<!-- Pass debug mode to JavaScript -->
<script>
    const POLLY_DEBUG = {{ POLLY_DEBUG|lower }};
</script>
<!-- Debug utilities -->
<script src="/static/polly-debug.js"></script>
```

### Template Context

All template responses now include debug context:

```python
return templates.TemplateResponse(
    "template.html",
    {
        "request": request,
        "POLLY_DEBUG": debug_context.get("debug_mode", False),
        # ... other context
    }
)
```

### Example Updates in Existing Templates

**Before:**
```javascript
console.warn('Emoji picker - Could not find input');
console.error('Error loading Discord emojis:', error);
```

**After:**
```javascript
PollyDebug.warn('Emoji picker - Could not find input');
PollyDebug.error('Error loading Discord emojis:', error);
```

## File Structure

```
polly/
├── debug_config.py              # Core debug configuration
├── main.py                      # Updated with debug initialization
├── web_app.py                   # Updated with debug context
├── discord_utils.py             # Updated to use debug logger
├── htmx_endpoints.py           # Updated to use debug logger
└── ...

static/
└── polly-debug.js              # Frontend debug utilities

templates/
├── dashboard_htmx.html         # Updated with debug script
└── htmx/
    └── create_form_filepond.html # Updated with PollyDebug calls

# Additional files
demo_debug_mode.py              # Demo script
DEBUG_MODE_INTEGRATION.md       # This documentation
```

## Testing and Validation

### Demo Script

Run the demo to see debug mode in action:
```bash
uv run python demo_debug_mode.py
```

### Manual Testing

1. **Enable Debug Mode:**
   ```bash
   # Set DEBUG=true in .env file
   uv run uvicorn polly.main:app --reload
   ```

2. **Check Backend Logging:**
   - Look for debug messages in console output
   - Check `logs/polly.log` for detailed logs

3. **Check Frontend Logging:**
   - Open browser developer tools (F12)
   - Look for styled debug messages with Polly branding
   - Interact with HTMX elements to see automatic logging

4. **Disable Debug Mode:**
   ```bash
   # Set DEBUG=false in .env file
   uv run uvicorn polly.main:app --reload
   ```

5. **Verify Silence:**
   - Debug messages should disappear from console
   - Browser console should be quiet (no PollyDebug output)

## Performance Considerations

### Debug Mode Enabled
- Slightly higher memory usage due to additional logging
- More I/O operations writing to log files
- Additional JavaScript processing for console formatting

### Debug Mode Disabled
- Minimal overhead - debug calls are short-circuited
- Clean production-ready logging
- No frontend debug processing

## Migration Guide

### For Existing Code

1. **Update logging imports:**
   ```python
   # Old
   import logging
   logger = logging.getLogger(__name__)
   
   # New
   from .debug_config import get_debug_logger
   logger = get_debug_logger(__name__)
   ```

2. **Update console logging in templates:**
   ```javascript
   // Old
   console.log("Debug info", data);
   console.warn("Warning message");
   
   // New
   PollyDebug.debug("Debug info", data);
   PollyDebug.warn("Warning message");
   ```

3. **Add debug context to templates:**
   ```python
   # Add POLLY_DEBUG to template context
   {"POLLY_DEBUG": debug_context.get("debug_mode", False)}
   ```

### Migration Priority

1. **High Priority:** Core modules (main.py, web_app.py, discord_utils.py)
2. **Medium Priority:** Endpoint handlers and utilities
3. **Low Priority:** Template JavaScript updates

## Benefits

1. **Unified Control:** Single environment variable controls all debugging
2. **Production Ready:** Easy to disable all debug output for production
3. **Developer Friendly:** Rich, styled console output aids development
4. **Performance Conscious:** Minimal overhead when disabled
5. **Consistent Logging:** Standardized logging patterns across backend and frontend
6. **Maintainable:** Centralized configuration makes updates easy

## Future Enhancements

Potential improvements for the debug system:

1. **Debug Levels:** Multiple debug levels (INFO, DEBUG, TRACE)
2. **Module Filtering:** Enable debug for specific modules only
3. **Log Rotation:** Automatic log file management
4. **Remote Logging:** Send debug logs to external services
5. **Debug Dashboard:** Web interface for runtime log level control
6. **Performance Metrics:** Integration with performance monitoring

## Conclusion

The DEBUG mode integration provides a robust foundation for development and production logging in Polly. It maintains clean separation between debug and production logging while providing rich debugging capabilities when needed. The system is designed to be performant, maintainable, and easy to use across the entire application stack.
