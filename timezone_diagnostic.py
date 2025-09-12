#!/usr/bin/env python3
"""
Timezone Diagnostic Script for Polly
Comprehensive timezone debugging and diagnostic tool that shows:
- Server timezone and current time
- All supported timezones with current times
- Poll timezone analysis
- Database timezone data
- System timezone configuration
"""

import os
import sys
import pytz
from datetime import datetime, timezone, timedelta
import time
import platform
from typing import Dict, List, Any

# Add the polly module to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from polly.database import get_db_session, Poll
    from polly.utils import validate_and_normalize_timezone, get_common_timezones, format_poll_closing_time
    POLLY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Polly modules not available: {e}")
    POLLY_AVAILABLE = False


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
        import time
        print(f"🐍 Python time.timezone: {time.timezone} seconds from UTC")
        print(f"🐍 Python time.daylight: {time.daylight}")
        print(f"🐍 Python time.altzone: {time.altzone} seconds from UTC")
    except Exception as e:
        print(f"❌ Error getting Python timezone info: {e}")


def show_major_timezones():
    """Show current time in major world timezones"""
    print_header("MAJOR WORLD TIMEZONES")
    
    major_timezones = [
        'UTC',
        'US/Eastern',
        'US/Central', 
        'US/Mountain',
        'US/Pacific',
        'Europe/London',
        'Europe/Paris',
        'Europe/Berlin',
        'Asia/Tokyo',
        'Asia/Shanghai',
        'Asia/Kolkata',
        'Australia/Sydney',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
    ]
    
    utc_now = datetime.now(pytz.UTC)
    
    for tz_name in major_timezones:
        try:
            tz = pytz.timezone(tz_name)
            local_time = utc_now.astimezone(tz)
            offset = local_time.strftime('%z')
            formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
            
            print(f"🌍 {tz_name:<20} | {local_time.strftime('%Y-%m-%d %H:%M:%S')} | {formatted_offset}")
        except Exception as e:
            print(f"❌ {tz_name:<20} | Error: {e}")


def show_polly_supported_timezones():
    """Show all Polly-supported timezones with current times"""
    if not POLLY_AVAILABLE:
        print("⚠️ Polly modules not available - skipping Polly timezone analysis")
        return
        
    print_header("POLLY SUPPORTED TIMEZONES")
    
    try:
        timezones = get_common_timezones()
        utc_now = datetime.now(pytz.UTC)
        
        print(f"📊 Total supported timezones: {len(timezones)}")
        print()
        
        for tz_info in timezones:
            tz_name = tz_info['name']
            display_name = tz_info['display']
            
            try:
                tz = pytz.timezone(tz_name)
                local_time = utc_now.astimezone(tz)
                
                print(f"🌍 {tz_name:<25} | {local_time.strftime('%Y-%m-%d %H:%M:%S')} | {display_name}")
            except Exception as e:
                print(f"❌ {tz_name:<25} | Error: {e}")
                
    except Exception as e:
        print(f"❌ Error getting Polly timezones: {e}")


def analyze_poll_timezones():
    """Analyze timezone usage in existing polls"""
    if not POLLY_AVAILABLE:
        print("⚠️ Polly modules not available - skipping poll timezone analysis")
        return
        
    print_header("POLL TIMEZONE ANALYSIS")
    
    try:
        db = get_db_session()
        
        # Get all polls with their timezones
        polls = db.query(Poll).all()
        
        if not polls:
            print("📊 No polls found in database")
            return
            
        print(f"📊 Total polls in database: {len(polls)}")
        
        # Analyze timezone usage
        timezone_usage = {}
        status_counts = {}
        timezone_by_status = {}
        
        for poll in polls:
            poll_tz = getattr(poll, 'timezone', 'UTC') or 'UTC'
            poll_status = getattr(poll, 'status', 'unknown')
            
            # Count timezone usage
            timezone_usage[poll_tz] = timezone_usage.get(poll_tz, 0) + 1
            
            # Count status
            status_counts[poll_status] = status_counts.get(poll_status, 0) + 1
            
            # Track timezone by status
            if poll_status not in timezone_by_status:
                timezone_by_status[poll_status] = {}
            timezone_by_status[poll_status][poll_tz] = timezone_by_status[poll_status].get(poll_tz, 0) + 1
        
        print_section("Poll Status Distribution")
        for status, count in sorted(status_counts.items()):
            print(f"📊 {status:<12} | {count:>4} polls")
        
        print_section("Timezone Usage Distribution")
        for tz, count in sorted(timezone_usage.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / len(polls)) * 100
            print(f"🌍 {tz:<25} | {count:>4} polls ({percentage:>5.1f}%)")
        
        print_section("Timezone by Poll Status")
        for status in sorted(timezone_by_status.keys()):
            print(f"\n📊 {status.upper()} POLLS:")
            for tz, count in sorted(timezone_by_status[status].items(), key=lambda x: x[1], reverse=True):
                print(f"   🌍 {tz:<20} | {count:>3} polls")
        
        # Show recent polls with their timezones
        print_section("Recent Polls (Last 10)")
        recent_polls = db.query(Poll).order_by(Poll.created_at.desc()).limit(10).all()
        
        utc_now = datetime.now(pytz.UTC)
        
        for poll in recent_polls:
            poll_id = getattr(poll, 'id', 'N/A')
            poll_name = getattr(poll, 'name', 'Unnamed')[:30]
            poll_tz = getattr(poll, 'timezone', 'UTC') or 'UTC'
            poll_status = getattr(poll, 'status', 'unknown')
            created_at = getattr(poll, 'created_at', None)
            
            if created_at:
                if created_at.tzinfo is None:
                    created_at = pytz.UTC.localize(created_at)
                created_str = created_at.strftime('%Y-%m-%d %H:%M:%S %Z')
            else:
                created_str = 'Unknown'
            
            print(f"📊 Poll {poll_id:<4} | {poll_status:<10} | {poll_tz:<20} | {poll_name:<30} | {created_str}")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error analyzing poll timezones: {e}")
        import traceback
        traceback.print_exc()


def test_timezone_functions():
    """Test Polly's timezone utility functions using the same logic as poll embeds"""
    if not POLLY_AVAILABLE:
        print("⚠️ Polly modules not available - skipping timezone function tests")
        return
        
    print_header("TIMEZONE FUNCTION TESTS")
    
    test_timezones = [
        'UTC',
        'US/Eastern',
        'US/Central',
        'Europe/London',
        'Asia/Tokyo',
        'EDT',  # Should normalize to US/Eastern
        'EST',  # Should normalize to US/Eastern
        'Invalid/Timezone',  # Should fallback to UTC
        '',  # Should fallback to UTC
        None,  # Should fallback to UTC
    ]
    
    print_section("Timezone Validation Tests (Same Logic as Poll Embeds)")
    for tz in test_timezones:
        try:
            normalized = validate_and_normalize_timezone(tz)
            print(f"🧪 {str(tz):<20} → {normalized}")
        except Exception as e:
            print(f"❌ {str(tz):<20} → Error: {e}")
    
    print_section("Poll Embed Timezone Logic Simulation")
    utc_now = datetime.now(pytz.UTC)
    
    # Test the exact logic used in create_poll_embed
    test_scenarios = [
        ("UTC timezone", "UTC", utc_now),
        ("US/Eastern timezone", "US/Eastern", utc_now),
        ("Europe/London timezone", "Europe/London", utc_now),
        ("Timezone-naive datetime", "US/Eastern", utc_now.replace(tzinfo=None)),
        ("Invalid timezone", "Invalid/Timezone", utc_now),
        ("Empty timezone", "", utc_now),
        ("None timezone", None, utc_now),
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
                    # Validate and normalize timezone first
                    normalized_tz = validate_and_normalize_timezone(poll_timezone)
                    
                    if normalized_tz != "UTC":
                        tz = pytz.timezone(normalized_tz)
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
    
    print_section("Time Formatting Tests (Same Logic as Poll Embeds)")
    utc_now = datetime.now(pytz.UTC)
    
    # Test future times
    tomorrow = utc_now + timedelta(days=1)
    test_times = [
        utc_now,  # Now
        utc_now.replace(hour=23, minute=59),  # Later today
        tomorrow.replace(hour=15, minute=30),  # Tomorrow afternoon
    ]
    
    for test_time in test_times:
        for tz_name in ['UTC', 'US/Eastern', 'Europe/London', 'Asia/Tokyo']:
            try:
                # Ensure test_time is timezone-aware before formatting
                if test_time.tzinfo is None:
                    test_time = pytz.UTC.localize(test_time)
                
                formatted = format_poll_closing_time(test_time, tz_name)
                normalized_tz = validate_and_normalize_timezone(tz_name)
                print(f"🕐 {test_time.strftime('%Y-%m-%d %H:%M:%S %Z')} in {normalized_tz:<15} → {formatted}")
            except Exception as e:
                print(f"❌ Error formatting time for {tz_name}: {e}")


def show_timezone_conversion_examples():
    """Show examples of timezone conversions"""
    print_header("TIMEZONE CONVERSION EXAMPLES")
    
    # Create test datetime
    utc_now = datetime.now(pytz.UTC)
    
    print(f"🕐 Base UTC Time: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print()
    
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
    
    for tz_name, description in conversion_examples:
        try:
            tz = pytz.timezone(tz_name)
            local_time = utc_now.astimezone(tz)
            offset = local_time.strftime('%z')
            formatted_offset = f"UTC{offset[:3]}:{offset[3:]}" if offset else "UTC"
            
            print(f"🌍 {description:<15} ({tz_name:<20}) | {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')} | {formatted_offset}")
        except Exception as e:
            print(f"❌ {description:<15} | Error: {e}")


def show_database_timezone_info():
    """Show timezone-related information from the database"""
    if not POLLY_AVAILABLE:
        print("⚠️ Polly modules not available - skipping database timezone info")
        return
        
    print_header("DATABASE TIMEZONE INFORMATION")
    
    try:
        db = get_db_session()
        
        # Check if we can query the database
        from sqlalchemy import text
        
        # Get database timezone
        try:
            result = db.execute(text("SELECT datetime('now') as current_time")).fetchone()
            if result:
                print(f"🗄️  Database Current Time: {result[0]}")
        except Exception as e:
            print(f"❌ Error getting database time: {e}")
        
        # Get timezone distribution in polls
        try:
            result = db.execute(text("""
                SELECT timezone, COUNT(*) as count 
                FROM polls 
                WHERE timezone IS NOT NULL 
                GROUP BY timezone 
                ORDER BY count DESC
            """)).fetchall()
            
            if result:
                print_section("Database Timezone Distribution")
                for row in result:
                    tz, count = row
                    print(f"🗄️  {tz:<25} | {count:>4} polls")
            else:
                print("📊 No timezone data found in polls table")
                
        except Exception as e:
            print(f"❌ Error querying timezone distribution: {e}")
        
        # Check for timezone-naive datetime fields
        try:
            result = db.execute(text("""
                SELECT 
                    COUNT(*) as total_polls,
                    COUNT(CASE WHEN open_time IS NOT NULL THEN 1 END) as polls_with_open_time,
                    COUNT(CASE WHEN close_time IS NOT NULL THEN 1 END) as polls_with_close_time,
                    COUNT(CASE WHEN created_at IS NOT NULL THEN 1 END) as polls_with_created_at
                FROM polls
            """)).fetchone()
            
            if result:
                total, open_time, close_time, created_at = result
                print_section("Database DateTime Field Analysis")
                print(f"🗄️  Total Polls: {total}")
                print(f"🗄️  Polls with open_time: {open_time}")
                print(f"🗄️  Polls with close_time: {close_time}")
                print(f"🗄️  Polls with created_at: {created_at}")
                
        except Exception as e:
            print(f"❌ Error analyzing datetime fields: {e}")
        
        db.close()
        
    except Exception as e:
        print(f"❌ Error accessing database: {e}")


def main():
    """Main diagnostic function"""
    print("🔍 POLLY TIMEZONE DIAGNOSTIC TOOL")
    print(f"⏰ Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # System timezone information
    get_system_timezone_info()
    
    # Major world timezones
    show_major_timezones()
    
    # Polly supported timezones
    show_polly_supported_timezones()
    
    # Poll timezone analysis
    analyze_poll_timezones()
    
    # Database timezone info
    show_database_timezone_info()
    
    # Timezone function tests
    test_timezone_functions()
    
    # Conversion examples
    show_timezone_conversion_examples()
    
    print_header("DIAGNOSTIC COMPLETE")
    print("✅ Timezone diagnostic completed successfully!")
    print("\n💡 Tips:")
    print("   - All poll times should be stored in UTC in the database")
    print("   - Poll timezone field should contain the user's selected timezone")
    print("   - Display times should be converted to poll timezone for user clarity")
    print("   - Always validate timezones before storing or converting")


if __name__ == "__main__":
    main()
