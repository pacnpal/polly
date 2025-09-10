#!/usr/bin/env python3

from datetime import datetime, timedelta
import pytz

def test_datetime_validation():
    """Test the datetime validation logic"""
    
    # Simulate the form data from the logs
    open_time_str = '2025-09-09T20:35'  # This is in local time (US/Eastern)
    close_time_str = '2025-09-09T20:44'  # This is in local time (US/Eastern)
    timezone_str = 'US/Eastern'
    
    # The log timestamp shows: 2025-09-10 00:35:06 UTC
    # Let's simulate this time
    current_utc = datetime(2025, 9, 10, 0, 35, 6, tzinfo=pytz.UTC)
    
    print(f"🔍 DATETIME VALIDATION TEST")
    print(f"Form open_time: {open_time_str}")
    print(f"Form close_time: {close_time_str}")
    print(f"Form timezone: {timezone_str}")
    print(f"Current UTC time (simulated): {current_utc}")
    
    # Parse the datetime as the validation function would
    try:
        # Parse the datetime string
        open_dt_naive = datetime.fromisoformat(open_time_str)
        print(f"Parsed open_time (naive): {open_dt_naive}")
        
        # Localize to user timezone
        user_tz = pytz.timezone(timezone_str)
        open_dt_local = user_tz.localize(open_dt_naive)
        print(f"Localized open_time: {open_dt_local}")
        
        # Convert to UTC
        open_dt_utc = open_dt_local.astimezone(pytz.UTC)
        print(f"Open time in UTC: {open_dt_utc}")
        
        # Check validation condition
        next_minute = current_utc.replace(second=0, microsecond=0) + timedelta(minutes=1)
        print(f"Next minute threshold: {next_minute}")
        
        is_in_past = open_dt_utc < next_minute
        print(f"Is open_time in the past? {is_in_past}")
        
        if is_in_past:
            print("❌ VALIDATION WOULD FAIL: Open time is in the past")
            return False
        else:
            print("✅ VALIDATION WOULD PASS: Open time is in the future")
            return True
            
    except Exception as e:
        print(f"❌ ERROR parsing datetime: {e}")
        return False

if __name__ == "__main__":
    test_datetime_validation()
