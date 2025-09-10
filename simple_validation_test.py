#!/usr/bin/env python3

# Simple test to check the validation logic without importing the full module

def test_role_ping_validation():
    """Test the role ping validation logic"""
    
    # Simulate the validation logic from the htmx_endpoints.py
    ping_role_enabled = "true" == "true"  # This should be True
    ping_role_id = "1412236527315976272"  # This should be a non-empty string
    
    print(f"🔍 ROLE PING VALIDATION TEST")
    print(f"ping_role_enabled: {ping_role_enabled} (type: {type(ping_role_enabled)})")
    print(f"ping_role_id: '{ping_role_id}' (type: {type(ping_role_id)})")
    print(f"ping_role_id stripped: '{ping_role_id.strip()}' (len: {len(ping_role_id.strip())})")
    
    # Test the validation condition
    validation_fails = ping_role_enabled and not ping_role_id
    print(f"ping_role_enabled and not ping_role_id: {validation_fails}")
    
    # Test with empty string
    empty_role_id = ""
    validation_fails_empty = ping_role_enabled and not empty_role_id
    print(f"With empty role_id - ping_role_enabled and not empty_role_id: {validation_fails_empty}")
    
    # Test with None
    none_role_id = None
    validation_fails_none = ping_role_enabled and not none_role_id
    print(f"With None role_id - ping_role_enabled and not none_role_id: {validation_fails_none}")
    
    return validation_fails

if __name__ == "__main__":
    test_role_ping_validation()
