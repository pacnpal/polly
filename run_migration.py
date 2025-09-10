#!/usr/bin/env python3
"""
Run database migration for Open Immediately feature
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from polly.migrations import migrate_database_if_needed

def main():
    print("🚀 Running database migration for Open Immediately feature...")
    print("=" * 60)
    
    success = migrate_database_if_needed()
    
    if success:
        print("✅ Database migration completed successfully!")
        print("🎉 Open Immediately feature is now fully supported!")
        return 0
    else:
        print("❌ Database migration failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
