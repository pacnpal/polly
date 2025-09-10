#!/usr/bin/env python3
"""
Demo: Polly DEBUG Mode Toggle
Shows how the DEBUG mode affects both backend logging and frontend context.
"""

import os
import sys
from pathlib import Path

# Add the polly module to the path
sys.path.insert(0, str(Path(__file__).parent / "polly"))

def demo_current_debug_status():
    """Show the current debug status and how it affects logging"""
    from polly.debug_config import get_debug_config, is_debug_mode, get_debug_logger, get_debug_context
    
    config = get_debug_config()
    
    print("🔍 Current DEBUG Mode Status:")
    print(f"   Environment DEBUG: {os.getenv('DEBUG', 'not set')}")
    print(f"   Debug mode active: {config.debug_mode}")
    print(f"   is_debug_mode(): {is_debug_mode()}")
    
    # Test logger
    logger = get_debug_logger("demo_module")
    print(f"   Logger effective level: {logger.getEffectiveLevel()} ({'DEBUG' if logger.getEffectiveLevel() <= 10 else 'INFO+'})")
    
    # Test frontend context
    frontend_context = get_debug_context()
    print(f"   Frontend context: {frontend_context}")
    print(f"   JavaScript POLLY_DEBUG would be: {str(frontend_context['debug_mode']).lower()}")
    
    return config

def demo_programmatic_toggle():
    """Show programmatic debug toggle"""
    from polly.debug_config import get_debug_config
    
    config = get_debug_config()
    
    print("\n🔧 Testing Programmatic Toggle:")
    original_state = config.debug_mode
    print(f"   Original state: {original_state}")
    
    # Toggle to opposite
    new_state = not original_state
    config.set_debug_mode(new_state)
    print(f"   After set_debug_mode({new_state}): {config.debug_mode}")
    
    # Toggle back
    config.set_debug_mode(original_state)
    print(f"   After set_debug_mode({original_state}): {config.debug_mode}")

def demo_logging_behavior():
    """Show how debug mode affects actual logging output"""
    from polly.debug_config import get_debug_logger
    
    logger = get_debug_logger("demo_logging")
    
    print("\n📝 Testing Logger Output:")
    print("   Trying different log levels...")
    
    logger.debug("🐛 This is a DEBUG message")
    logger.info("ℹ️  This is an INFO message")
    logger.warning("⚠️  This is a WARNING message")
    logger.error("❌ This is an ERROR message")

def main():
    """Run the demo"""
    print("🚀 Polly DEBUG Mode Integration Demo\n")
    
    # Show current status
    config = demo_current_debug_status()
    
    # Show programmatic control
    demo_programmatic_toggle()
    
    # Show logging behavior
    demo_logging_behavior()
    
    print("\n✅ Integration Summary:")
    if config.debug_mode:
        print("   🐛 DEBUG MODE is ENABLED")
        print("      • Backend: Debug-level logging is active")
        print("      • Frontend: PollyDebug.* methods will output to console")
        print("      • HTMX: Automatic request/response logging enabled")
    else:
        print("   📊 DEBUG MODE is DISABLED")
        print("      • Backend: Standard INFO+ logging only")
        print("      • Frontend: PollyDebug.* methods are silenced")
        print("      • HTMX: No automatic request logging")
    
    print(f"\n💡 To toggle: Set DEBUG={str(not config.debug_mode).lower()} in your .env file")
    print("   Then restart the application: uv run uvicorn polly.main:app --reload")

if __name__ == "__main__":
    main()
