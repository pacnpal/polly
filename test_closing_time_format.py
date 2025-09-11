#!/usr/bin/env python3
"""
Test script to verify the new poll closing time formatting functionality.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'polly'))

from datetime import datetime, timedelta
import pytz
from polly.utils import format_poll_closing_time

def test_closing_time_formatting():
    """Test the format_poll_closing_time function with various scenarios"""
    
    # Test timezone
    test_tz = "US/Eastern"
    tz = pytz.timezone(test_tz)
    
    # Get current time in the test timezone
    now = datetime.now(tz)
    
    print(f"Testing with timezone: {test_tz}")
    print(f"Current time: {now.strftime('%Y-%m-%d %I:%M %p %Z')}")
    print("-" * 50)
    
    # Test cases
    test_cases = [
        ("Today at 2:30 PM", now.replace(hour=14, minute=30, second=0, microsecond=0)),
        ("Today at 11:45 PM", now.replace(hour=23, minute=45, second=0, microsecond=0)),
        ("Tomorrow at 9:00 AM", (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)),
        ("Tomorrow at 6:30 PM", (now + timedelta(days=1)).replace(hour=18, minute=30, second=0, microsecond=0)),
        ("Day after tomorrow", (now + timedelta(days=2)).replace(hour=15, minute=0, second=0, microsecond=0)),
        ("Next week", (now + timedelta(days=7)).replace(hour=12, minute=0, second=0, microsecond=0)),
    ]
    
    for description, test_time in test_cases:
        # Convert to UTC for storage (as the system would do)
        utc_time = test_time.astimezone(pytz.UTC)
        
        # Format using our function
        formatted = format_poll_closing_time(utc_time, test_tz)
        
        print(f"{description:20} -> {formatted}")
    
    print("-" * 50)
    print("Testing with different timezones:")
    
    # Test with different timezones
    timezones = ["US/Pacific", "Europe/London", "Asia/Tokyo", "UTC"]
    base_time = datetime.now(pytz.UTC) + timedelta(hours=2)  # 2 hours from now
    
    for tz_name in timezones:
        formatted = format_poll_closing_time(base_time, tz_name)
        print(f"{tz_name:15} -> {formatted}")

if __name__ == "__main__":
    test_closing_time_formatting()
