#!/usr/bin/env python3
"""
Run database migration for Open Immediately feature
"""

import sys
import os
import shutil
from pathlib import Path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from polly.migrations import migrate_database_if_needed

def main():
    print("🚀 Running database migration for Open Immediately feature...")
    print("=" * 60)
    
    # Clean up cache directory before migration
    cache_dir = Path(".cache")
    if cache_dir.exists() and cache_dir.is_dir():
        try:
            shutil.rmtree(cache_dir)
            print("🗑️ Removed .cache directory before migration")
        except Exception as e:
            print(f"⚠️ Failed to remove .cache directory: {e}")
    
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
