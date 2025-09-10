#!/usr/bin/env python3
"""
Test script to force regenerate incompatible static pages
"""

import asyncio
import sys
import os

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.static_page_generator import get_static_page_generator

async def main():
    """Test the force regeneration functionality"""
    print("🔄 Starting force regeneration of incompatible static pages...")
    
    try:
        generator = get_static_page_generator()
        results = await generator.force_regenerate_incompatible_static_pages()
        
        print("\n📊 RESULTS:")
        print(f"Total polls checked: {results['total_polls']}")
        print(f"Incompatible found: {results['incompatible']}")
        print(f"Successfully regenerated: {results['regenerated']}")
        print(f"Failed: {results['failed']}")
        
        if results.get('error'):
            print(f"❌ Error: {results['error']}")
            return False
        
        if results['details']:
            print("\n📋 DETAILS:")
            for detail in results['details']:
                poll_id = detail['poll_id']
                status = detail['status']
                
                if status == 'success':
                    reasons = ', '.join(detail['reasons'])
                    print(f"  ✅ Poll {poll_id}: Regenerated ({reasons})")
                elif status == 'failed':
                    reasons = ', '.join(detail['reasons'])
                    print(f"  ❌ Poll {poll_id}: Failed ({reasons})")
                elif status == 'already_compatible':
                    print(f"  ✅ Poll {poll_id}: Already compatible")
                elif status == 'error':
                    print(f"  ❌ Poll {poll_id}: Error - {detail['error']}")
        
        print(f"\n🏁 Force regeneration completed!")
        return results['failed'] == 0
        
    except Exception as e:
        print(f"❌ Error during force regeneration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
