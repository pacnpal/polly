#!/usr/bin/env python3
"""
Simple Timezone Diagnostic Script
Standalone timezone debugging tool that doesn't require Polly modules.
Shows system timezone info and major world timezones.
"""

import os
import sys
import pytz
from datetime import datetime, timezone, timedelta
import time
import platform


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'-'*40}")
    print(f"  {title}")
    print(f"{'-'*40}")


def get_system_timezone_info():
    """Get comprehensive system timezone information"""
    print_header("SYSTEM TIMEZONE INFORMATION")
    
    # Current UTC time
    utc_now = datetime.now(timezone.utc)
    print(f"🌍 Current UTC Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # System local time
    local_now = datetime.now()
    print(f"🖥️  System Local Time: {local_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # System timezone
    try:
        system_tz = time.tzname
        print(f"🖥️  System Timezone Names: {system_tz}")
    except Exception as e:
        print(f"❌ Error getting system timezone: {e}")
    
    # Platform info
    print(f"🖥️  Platform: {platform.system()} {platform.release()}")
    
    # Environment timezone variables
    print(f"🌍 TZ Environment Variable: {os.environ.get('TZ', 'Not set')}")
    
    # Python timezone info
    try:
        print(f"🐍 Python time.timezone: {time.timezone} seconds from UTC")
        print(f"🐍 Python time.daylight: {time.daylight}")
        print(f"🐍 Python time.altzone: {time.altzone} seconds from UTC")
    except Exception as e:
        print(f"❌ Error getting Python timezone info: {e}")
    
    # Calculate system timezone offset
    try:
        local_offset = local_now.astimezone().utcoffset()
        if local_offset:
            hours, remainder = divmod(int(local_offset.total_seconds()), 3600)
            minutes = remainder // 60
            offset_str = f"UTC{hours:+03d}:{minutes:02d}"
            print(f"🖥️  System UTC Offset: {offset_str}")
    except Exception as e:
        print(f"❌ Error calculating system offset: {e}")


def show_major_timezones():
    """Show current time in major world timezones"""
    print_header("MAJOR WORLD TIMEZONES")
    
    major_timezones = [
        'UTC',
        'US/Eastern',
        'US/Central', 
        'US/Mountain',
        'US/Pacific',
        'US/Alaska',
        'US/Hawaii',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Europe/Rome',
        'Europe/Moscow',
        'Asia/Tokyo',
        'Asia/Shanghai',
        'Asia/Seoul',
        'Asia/Kolkata',
        'Asia/Dubai',
        'Australia/Sydney',
        'Australia/Melbourne',
        'Pacific/Auckland',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'America/Toronto',
        'America/Mexico_City',
        'America/Sao_Paulo',
    ]
    
    utc_now = datetime.now(pytz.UTC)
    
    print(f"🕐 Base UTC Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    
    for tz_name in major_timezones:
        try:
            tz = pytz.timezone(tz_name)
            local_time = utc_now.astimezone(tz)
            offset = local_time.strftime('%z')
            formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
            
            # Check if it's DST
            is_dst = bool(local_time.dst())
            dst_indicator = " (DST)" if is_dst else ""
            
            print(f"🌍 {tz_name:<25} | {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')} | {formatted_offset}{dst_indicator}")
        except Exception as e:
            print(f"❌ {tz_name:<25} | Error: {e}")


def show_timezone_conversion_examples():
    """Show examples of timezone conversions"""
    print_header("TIMEZONE CONVERSION EXAMPLES")
    
    # Create test datetimes
    utc_now = datetime.now(pytz.UTC)
    
    print(f"🕐 Base UTC Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    
    # Test different times of day
    test_times = [
        utc_now.replace(hour=0, minute=0, second=0, microsecond=0),   # Midnight UTC
        utc_now.replace(hour=12, minute=0, second=0, microsecond=0),  # Noon UTC
        utc_now.replace(hour=18, minute=30, second=0, microsecond=0), # 6:30 PM UTC
    ]
    
    conversion_examples = [
        ('US/Eastern', 'Eastern Time'),
        ('US/Central', 'Central Time'),
        ('US/Mountain', 'Mountain Time'),
        ('US/Pacific', 'Pacific Time'),
        ('Europe/London', 'London Time'),
        ('Europe/Paris', 'Paris Time'),
        ('Asia/Tokyo', 'Tokyo Time'),
        ('Australia/Sydney', 'Sydney Time'),
    ]
    
    for test_time in test_times:
        print_section(f"Converting {test_time.strftime('%H:%M:%S UTC')}")
        
        for tz_name, description in conversion_examples:
            try:
                tz = pytz.timezone(tz_name)
                local_time = test_time.astimezone(tz)
                offset = local_time.strftime('%z')
                formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
                
                print(f"🌍 {description:<15} | {local_time.strftime('%H:%M:%S %Z')} | {formatted_offset}")
            except Exception as e:
                print(f"❌ {description:<15} | Error: {e}")


def test_timezone_edge_cases():
    """Test timezone edge cases and DST transitions"""
    print_header("TIMEZONE EDGE CASES & DST TRANSITIONS")
    
    # Test DST transition dates (approximate - varies by year)
    utc_now = datetime.now(pytz.UTC)
    current_year = utc_now.year
    
    # Spring forward (second Sunday in March for US)
    spring_forward = datetime(current_year, 3, 8, 7, 0, 0)  # 2 AM EST becomes 3 AM EDT
    spring_forward = pytz.UTC.localize(spring_forward)
    
    # Fall back (first Sunday in November for US)  
    fall_back = datetime(current_year, 11, 1, 6, 0, 0)  # 2 AM EDT becomes 1 AM EST
    fall_back = pytz.UTC.localize(fall_back)
    
    test_cases = [
        ("Current Time", utc_now),
        ("Spring DST Transition", spring_forward),
        ("Fall DST Transition", fall_back),
    ]
    
    dst_timezones = ['US/Eastern', 'US/Central', 'US/Pacific', 'Europe/London', 'Europe/Paris']
    
    for case_name, test_time in test_cases:
        print_section(case_name)
        print(f"🕐 UTC Time: {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        for tz_name in dst_timezones:
            try:
                tz = pytz.timezone(tz_name)
                local_time = test_time.astimezone(tz)
                is_dst = bool(local_time.dst())
                dst_offset = local_time.dst()
                
                offset = local_time.strftime('%z')
                formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
                dst_info = f" (DST: {is_dst}, offset: {dst_offset})" if dst_offset else " (No DST)"
                
                print(f"🌍 {tz_name:<15} | {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')} | {formatted_offset}{dst_info}")
            except Exception as e:
                print(f"❌ {tz_name:<15} | Error: {e}")


def show_pytz_info():
    """Show PyTz library information"""
    print_header("PYTZ LIBRARY INFORMATION")
    
    try:
        print(f"🐍 PyTz Version: {pytz.__version__}")
        print(f"🌍 Total Timezones Available: {len(pytz.all_timezones)}")
        print(f"🌍 Common Timezones: {len(pytz.common_timezones)}")
        
        print_section("Sample of All Available Timezones")
        sample_timezones = sorted(list(pytz.all_timezones))[:20]  # First 20
        for tz in sample_timezones:
            print(f"🌍 {tz}")
        print(f"... and {len(pytz.all_timezones) - 20} more")
        
        print_section("UTC Timezone Info")
        utc_tz = pytz.UTC
        utc_now = datetime.now(utc_tz)
        print(f"🌍 UTC Timezone Object: {utc_tz}")
        print(f"🕐 Current UTC Time: {utc_now}")
        print(f"🕐 UTC Offset: {utc_now.utcoffset()}")
        print(f"🕐 DST Offset: {utc_now.dst()}")
        
    except Exception as e:
        print(f"❌ Error getting PyTz info: {e}")


def test_datetime_operations():
    """Test various datetime operations using poll embed logic patterns"""
    print_header("DATETIME OPERATIONS TESTS")
    
    # Test timezone-naive vs timezone-aware
    print_section("Timezone-Naive vs Timezone-Aware")
    
    naive_dt = datetime.now()
    aware_dt = datetime.now(pytz.UTC)
    
    print(f"🕐 Timezone-Naive: {naive_dt} (tzinfo: {naive_dt.tzinfo})")
    print(f"🕐 Timezone-Aware:  {aware_dt} (tzinfo: {aware_dt.tzinfo})")
    
    # Test localization
    print_section("Timezone Localization")
    
    try:
        # Localize naive datetime to different timezones
        test_timezones = ['UTC', 'US/Eastern', 'Europe/London', 'Asia/Tokyo']
        
        for tz_name in test_timezones:
            tz = pytz.timezone(tz_name)
            localized = tz.localize(naive_dt)
            print(f"🌍 {tz_name:<15} | {localized.strftime('%Y-%m-%d %H:%M:%S %Z')} | Offset: {localized.utcoffset()}")
    except Exception as e:
        print(f"❌ Error in localization test: {e}")
    
    # Test conversion between timezones
    print_section("Timezone Conversion")
    
    try:
        eastern = pytz.timezone('US/Eastern')
        pacific = pytz.timezone('US/Pacific')
        
        # Create a time in Eastern
        eastern_time = eastern.localize(datetime(2025, 6, 15, 14, 30, 0))  # 2:30 PM Eastern
        
        # Convert to other timezones
        utc_time = eastern_time.astimezone(pytz.UTC)
        pacific_time = eastern_time.astimezone(pacific)
        
        print(f"🌍 Original (Eastern): {eastern_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"🌍 Converted to UTC:   {utc_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"🌍 Converted to Pacific: {pacific_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
    except Exception as e:
        print(f"❌ Error in conversion test: {e}")
    
    # Test poll embed timezone logic simulation
    print_section("Poll Embed Timezone Logic Simulation")
    
    # Simulate the exact logic used in create_poll_embed
    test_scenarios = [
        ("UTC timezone", "UTC", aware_dt),
        ("US/Eastern timezone", "US/Eastern", aware_dt),
        ("Europe/London timezone", "Europe/London", aware_dt),
        ("Timezone-naive datetime", "US/Eastern", naive_dt),
        ("Invalid timezone", "Invalid/Timezone", aware_dt),
        ("Empty timezone", "", aware_dt),
        ("None timezone", None, aware_dt),
    ]
    
    for scenario_name, poll_timezone, poll_timestamp in test_scenarios:
        print(f"\n🧪 Testing: {scenario_name}")
        print(f"   Input timezone: {poll_timezone}")
        print(f"   Input timestamp: {poll_timestamp}")
        
        try:
            # Simulate the exact logic from create_poll_embed
            processed_timestamp = poll_timestamp
            
            # Ensure timestamp is timezone-aware (should be UTC from database)
            if processed_timestamp.tzinfo is None:
                print(f"   ⚠️ Timezone-naive timestamp detected, assuming UTC")
                processed_timestamp = pytz.UTC.localize(processed_timestamp)
            
            # Convert timestamp to poll's timezone for display if specified and different from UTC
            if poll_timezone and poll_timezone != "UTC":
                try:
                    # Basic timezone validation (simplified since we don't have validate_and_normalize_timezone)
                    try:
                        tz = pytz.timezone(poll_timezone)
                        normalized_tz = poll_timezone
                    except pytz.exceptions.UnknownTimeZoneError:
                        print(f"   ❌ Unknown timezone: {poll_timezone}, falling back to UTC")
                        normalized_tz = "UTC"
                        tz = pytz.UTC
                    
                    if normalized_tz != "UTC":
                        # Convert to the poll's timezone for display
                        processed_timestamp = processed_timestamp.astimezone(tz)
                        print(f"   ✅ Converted to {normalized_tz}: {processed_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                    else:
                        print(f"   ℹ️ Using UTC (normalized from {poll_timezone})")
                        
                except Exception as e:
                    print(f"   ❌ Timezone conversion failed: {e}")
                    # Ensure we have a valid UTC timestamp as fallback
                    if processed_timestamp.tzinfo != pytz.UTC:
                        processed_timestamp = processed_timestamp.astimezone(pytz.UTC)
                    print(f"   ⚠️ Using UTC fallback: {processed_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            else:
                print(f"   ℹ️ Using UTC timezone: {processed_timestamp.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
        except Exception as e:
            print(f"   ❌ Scenario failed: {e}")


def main():
    """Main diagnostic function"""
    print("🔍 SIMPLE TIMEZONE DIAGNOSTIC TOOL")
    print(f"⏰ Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🖥️  Running on: {platform.system()} {platform.release()}")
    
    # System timezone information
    get_system_timezone_info()
    
    # PyTz library info
    show_pytz_info()
    
    # Major world timezones
    show_major_timezones()
    
    # Conversion examples
    show_timezone_conversion_examples()
    
    # Edge cases and DST
    test_timezone_edge_cases()
    
    # DateTime operations
    test_datetime_operations()
    
    print_header("DIAGNOSTIC COMPLETE")
    print("✅ Simple timezone diagnostic completed successfully!")
    print("\n💡 Key Findings:")
    print("   - Check if system timezone matches expected timezone")
    print("   - Verify UTC time is correct")
    print("   - Ensure DST transitions are handled properly")
    print("   - All stored times should be in UTC")
    print("   - Display times should be converted to user's timezone")
    
    print("\n🔧 Usage:")
    print("   python simple_timezone_diagnostic.py")
    print("   python timezone_diagnostic.py  # For full Polly integration")


if __name__ == "__main__":
    main()
