#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from polly.htmx_endpoints import validate_poll_form_data

# Create mock form data that should trigger validation errors
class MockFormData:
    def __init__(self, data):
        self.data = data
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def keys(self):
        return self.data.keys()
    
    def items(self):
        return self.data.items()

# Test with the exact form data from the logs
form_data = MockFormData({
    'name': 'Copy of Todays poll',
    'timezone': 'US/Eastern',
    'question': 'Wood or Steel?',
    'server_id': '1067616268385009736',
    'channel_id': '1102998270961258616',
    'option1': 'Wood',
    'emoji1': '🇦',
    'option2': 'Steel',
    'emoji2': '🇧',
    'open_time': '2025-09-09T20:35',
    'close_time': '2025-09-09T20:44',
    'image': None,  # No image for this test
    'image_message_text': 'ok',
    'anonymous': 'true',
    'ping_role_enabled': 'true',
    'ping_role_id': '1412236527315976272'
})

print("🔍 VALIDATION TEST - Testing form data validation")
print(f"Form data: {dict(form_data.data)}")

# Test validation
is_valid, validation_errors, validated_data = validate_poll_form_data(form_data, "141517468408610816")

print(f"\n🔍 VALIDATION RESULTS:")
print(f"is_valid: {is_valid}")
print(f"validation_errors count: {len(validation_errors)}")
print(f"validated_data keys: {list(validated_data.keys())}")

if validation_errors:
    print(f"\n🔍 VALIDATION ERRORS:")
    for i, error in enumerate(validation_errors):
        print(f"Error {i + 1}: {error}")

print(f"\n🔍 VALIDATED DATA:")
for key, value in validated_data.items():
    print(f"{key}: {value}")
