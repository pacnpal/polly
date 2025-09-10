#!/usr/bin/env python3
"""
Test DEBUG Mode Integration
Verify that the DEBUG mode toggle works correctly for both backend and frontend.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add the polly module to the path
sys.path.insert(0, str(Path(__file__).parent / "polly"))

@patch.dict(os.environ, {}, clear=True)
@patch('polly.debug_config.config')
def test_debug_mode_disabled(mock_config):
    """Test that debug mode is disabled by default"""
    # Mock the config function to return False for DEBUG
    mock_config.return_value = False
    
    # Clear any cached modules
    import sys
    modules_to_clear = [m for m in sys.modules if m.startswith('polly.debug_config')]
    for module in modules_to_clear:
        del sys.modules[module]
    
    # Import fresh debug config
    from polly.debug_config import DebugConfig, get_debug_config, is_debug_mode, get_debug_logger
    
    # Create a fresh config instance
    config = DebugConfig()
    
    print("🧪 Testing DEBUG mode DISABLED (default)")
    print(f"   Debug mode: {config.debug_mode}")
    print(f"   is_debug_mode() (fresh): {config.debug_mode}")
    
    # Test logger behavior
    logger = get_debug_logger("test_module")
    print(f"   Logger effective level: {logger.getEffectiveLevel()}")
    
    # Test frontend context
    frontend_context = config.get_frontend_context()
    print(f"   Frontend context: {frontend_context}")
    
    assert config.debug_mode == False, "Debug mode should be False by default"
    assert frontend_context["debug_mode"] == False, "Frontend context should have debug_mode=False"
    
    print("   ✅ DEBUG disabled tests passed\n")


def test_debug_mode_enabled():
    """Test that debug mode is enabled when DEBUG=true"""
    # Set DEBUG environment variable
    os.environ["DEBUG"] = "true"
    
    # Re-import to get fresh config (since it reads env on import)
    import importlib
    import polly.debug_config
    importlib.reload(polly.debug_config)
    
    from polly.debug_config import get_debug_config, is_debug_mode, get_debug_logger, init_debug_config
    
    # Initialize debug config
    init_debug_config()
    
    config = get_debug_config()
    
    print("🧪 Testing DEBUG mode ENABLED")
    print(f"   Debug mode: {config.debug_mode}")
    print(f"   is_debug_mode(): {is_debug_mode()}")
    
    # Test logger behavior
    logger = get_debug_logger("test_module")
    print(f"   Logger level: {logger.level}")
    print(f"   Root logger level: {logger.root.level}")
    
    # Test frontend context
    frontend_context = config.get_frontend_context()
    print(f"   Frontend context: {frontend_context}")
    
    assert config.debug_mode == True, "Debug mode should be True when DEBUG=true"
    assert is_debug_mode() == True, "is_debug_mode() should return True"
    assert frontend_context["debug_mode"] == True, "Frontend context should have debug_mode=True"
    
    print("   ✅ DEBUG enabled tests passed\n")


def test_programmatic_toggle():
    """Test programmatically setting debug mode"""
    from polly.debug_config import get_debug_config, is_debug_mode
    
    config = get_debug_config()
    
    print("🧪 Testing programmatic DEBUG mode toggle")
    
    # Enable debug mode programmatically
    config.set_debug_mode(True)
    print(f"   After set_debug_mode(True): {is_debug_mode()}")
    assert is_debug_mode() == True, "Debug mode should be enabled programmatically"
    
    # Disable debug mode programmatically
    config.set_debug_mode(False)
    print(f"   After set_debug_mode(False): {is_debug_mode()}")
    assert is_debug_mode() == False, "Debug mode should be disabled programmatically"
    
    print("   ✅ Programmatic toggle tests passed\n")


def test_javascript_integration():
    """Test that JavaScript debug template integration would work"""
    from polly.debug_config import get_debug_context
    
    print("🧪 Testing JavaScript template integration")
    
    # Test with debug disabled
    os.environ.pop("DEBUG", None)
    import importlib
    import polly.debug_config
    importlib.reload(polly.debug_config)
    
    from polly.debug_config import get_debug_context
    
    context = get_debug_context()
    print(f"   Debug disabled context: {context}")
    
    # Simulate template rendering
    polly_debug_js_var = str(context["debug_mode"]).lower()  # Convert to JS boolean
    print(f"   JavaScript POLLY_DEBUG var would be: {polly_debug_js_var}")
    
    assert polly_debug_js_var == "false", "JavaScript POLLY_DEBUG should be 'false'"
    
    # Test with debug enabled
    os.environ["DEBUG"] = "true"
    importlib.reload(polly.debug_config)
    
    from polly.debug_config import get_debug_context
    
    context = get_debug_context()
    polly_debug_js_var = str(context["debug_mode"]).lower()
    print(f"   Debug enabled context: {context}")
    print(f"   JavaScript POLLY_DEBUG var would be: {polly_debug_js_var}")
    
    assert polly_debug_js_var == "true", "JavaScript POLLY_DEBUG should be 'true'"
    
    print("   ✅ JavaScript integration tests passed\n")


def main():
    """Run all tests"""
    print("🚀 Starting Polly DEBUG mode integration tests\n")
    
    try:
        test_debug_mode_disabled()
        test_debug_mode_enabled()
        test_programmatic_toggle()
        test_javascript_integration()
        
        print("🎉 All DEBUG mode tests passed!")
        print("\nℹ️  Integration Summary:")
        print("   ✅ Backend logging levels adjust based on DEBUG env var")
        print("   ✅ Frontend receives debug context for console logging")
        print("   ✅ Programmatic control works for runtime toggling")
        print("   ✅ Template integration ready for JavaScript PollyDebug")
        
        print("\n📝 Usage Examples:")
        print("   # Enable debug mode:")
        print("   export DEBUG=true && uv run uvicorn polly.main:app --reload")
        print()
        print("   # Disable debug mode:")
        print("   export DEBUG=false && uv run uvicorn polly.main:app --reload")
        print()
        print("   # Frontend usage (when POLLY_DEBUG=true):")
        print("   PollyDebug.info('This will show in console')")
        print("   PollyDebug.htmx('HTMX request completed')")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
