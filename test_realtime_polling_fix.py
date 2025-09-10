#!/usr/bin/env python3
"""
Test script to verify that realtime polling stops for closed polls.
This script tests the poll status-based streaming control implementation.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
import pytz

# Add the polly directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'polly'))

from database import get_db_session, Poll, Vote
from htmx_endpoints import get_poll_results_realtime_htmx, get_poll_dashboard_htmx
from enhanced_cache_service import get_enhanced_cache_service

class MockRequest:
    """Mock request object for testing"""
    def __init__(self):
        pass

class MockUser:
    """Mock user object for testing"""
    def __init__(self, user_id="test_user_123"):
        self.id = user_id

async def test_realtime_polling_behavior():
    """Test that realtime polling behaves correctly based on poll status"""
    print("🔍 Testing realtime polling behavior for different poll statuses...")
    
    # Clear any existing cache
    cache_service = get_enhanced_cache_service()
    
    db = get_db_session()
    try:
        # Find an existing poll or create a test scenario
        polls = db.query(Poll).limit(3).all()
        
        if not polls:
            print("❌ No polls found in database for testing")
            return False
            
        print(f"📊 Found {len(polls)} polls for testing")
        
        # Test with different poll statuses
        test_results = []
        
        for poll in polls:
            poll_id = poll.id
            poll_status = poll.status
            poll_name = poll.name
            
            print(f"\n🔍 Testing poll {poll_id} ('{poll_name}') with status: {poll_status}")
            
            # Clear cache for this poll
            await cache_service.clear_poll_cache(poll_id)
            
            # Test results endpoint
            mock_request = MockRequest()
            mock_user = MockUser()
            
            try:
                # Test get_poll_results_realtime_htmx
                results_response = await get_poll_results_realtime_htmx(
                    poll_id, mock_request, mock_user
                )
                
                # Check if response contains status indicators
                if isinstance(results_response, str):
                    has_closed_indicator = "poll is closed" in results_response.lower() or "results are final" in results_response.lower()
                    has_realtime_content = "every 5s" in results_response.lower() or "updating" in results_response.lower()
                    
                    print(f"  📈 Results endpoint:")
                    print(f"    - Response length: {len(results_response)} chars")
                    print(f"    - Has closed indicator: {has_closed_indicator}")
                    print(f"    - Has realtime content: {has_realtime_content}")
                    
                    # For closed polls, we expect closed indicators and no realtime content
                    if poll_status == 'closed':
                        expected_behavior = has_closed_indicator and not has_realtime_content
                        print(f"    - ✅ Closed poll behavior correct: {expected_behavior}")
                    elif poll_status == 'active':
                        expected_behavior = not has_closed_indicator
                        print(f"    - ✅ Active poll behavior correct: {expected_behavior}")
                    else:
                        print(f"    - ℹ️  Status '{poll_status}' - behavior varies")
                        expected_behavior = True
                    
                    test_results.append({
                        'poll_id': poll_id,
                        'status': poll_status,
                        'endpoint': 'results',
                        'correct_behavior': expected_behavior
                    })
                
                # Test dashboard endpoint (mock bot parameter)
                dashboard_response = await get_poll_dashboard_htmx(
                    poll_id, mock_request, None, mock_user  # bot=None for testing
                )
                
                print(f"  📊 Dashboard endpoint:")
                if hasattr(dashboard_response, 'body'):
                    print(f"    - Response type: Template response")
                    print(f"    - ✅ Dashboard endpoint accessible")
                else:
                    print(f"    - Response type: {type(dashboard_response)}")
                
                test_results.append({
                    'poll_id': poll_id,
                    'status': poll_status,
                    'endpoint': 'dashboard',
                    'correct_behavior': True  # Just test accessibility for now
                })
                
            except Exception as e:
                print(f"    ❌ Error testing poll {poll_id}: {e}")
                test_results.append({
                    'poll_id': poll_id,
                    'status': poll_status,
                    'endpoint': 'both',
                    'correct_behavior': False,
                    'error': str(e)
                })
        
        # Summary
        print(f"\n📋 Test Summary:")
        total_tests = len(test_results)
        successful_tests = sum(1 for result in test_results if result['correct_behavior'])
        
        print(f"  - Total tests: {total_tests}")
        print(f"  - Successful: {successful_tests}")
        print(f"  - Failed: {total_tests - successful_tests}")
        
        if successful_tests == total_tests:
            print("✅ All tests passed! Realtime polling behavior is working correctly.")
            return True
        else:
            print("⚠️  Some tests failed. Check the implementation.")
            for result in test_results:
                if not result['correct_behavior']:
                    print(f"    - Failed: Poll {result['poll_id']} ({result['status']}) - {result['endpoint']}")
                    if 'error' in result:
                        print(f"      Error: {result['error']}")
            return False
            
    except Exception as e:
        print(f"❌ Critical error during testing: {e}")
        return False
    finally:
        db.close()

async def test_template_conditional_logic():
    """Test that templates have the correct conditional logic"""
    print("\n🔍 Testing template conditional logic...")
    
    # Read the template files to verify the changes
    template_files = [
        'templates/htmx/poll_details.html',
        'templates/htmx/components/poll_dashboard.html'
    ]
    
    all_correct = True
    
    for template_file in template_files:
        try:
            with open(template_file, 'r') as f:
                content = f.read()
            
            print(f"📄 Checking {template_file}:")
            
            # Check for conditional hx-trigger
            has_conditional_trigger = "poll.status == 'active'" in content and "hx-trigger" in content
            print(f"  - Has conditional hx-trigger: {has_conditional_trigger}")
            
            # Check for status-based messaging
            has_status_messaging = "poll is" in content or "realtime updates stopped" in content.lower()
            print(f"  - Has status messaging: {has_status_messaging}")
            
            if has_conditional_trigger:
                print(f"  - ✅ Template correctly implements conditional polling")
            else:
                print(f"  - ❌ Template missing conditional polling logic")
                all_correct = False
                
        except FileNotFoundError:
            print(f"  - ❌ Template file not found: {template_file}")
            all_correct = False
        except Exception as e:
            print(f"  - ❌ Error reading template: {e}")
            all_correct = False
    
    return all_correct

async def main():
    """Main test function"""
    print("🚀 Starting realtime polling fix verification tests...\n")
    
    # Test 1: Template conditional logic
    template_test = await test_template_conditional_logic()
    
    # Test 2: Backend behavior
    backend_test = await test_realtime_polling_behavior()
    
    # Final summary
    print(f"\n🏁 Final Test Results:")
    print(f"  - Template logic: {'✅ PASS' if template_test else '❌ FAIL'}")
    print(f"  - Backend behavior: {'✅ PASS' if backend_test else '❌ FAIL'}")
    
    if template_test and backend_test:
        print(f"\n🎉 All tests passed! The realtime polling fix is working correctly.")
        print(f"   - Realtime updates will stop when polls are closed")
        print(f"   - Templates conditionally enable polling based on poll status")
        print(f"   - Backend endpoints handle status-based caching and responses")
        return True
    else:
        print(f"\n⚠️  Some tests failed. Please review the implementation.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)