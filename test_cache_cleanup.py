#!/usr/bin/env python3
"""
Test script to verify that .cache directory is deleted during database migrations
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from polly.migrations import DatabaseMigrator

def test_cache_cleanup():
    """Test that cache cleanup works during migrations"""
    print("🧪 Testing cache cleanup during migrations...")
    print("=" * 50)
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        
        # Change to test directory
        original_cwd = os.getcwd()
        os.chdir(test_dir)
        
        try:
            # Create a fake .cache directory with some content
            cache_dir = test_dir / ".cache"
            cache_dir.mkdir()
            
            # Add some fake cache files
            (cache_dir / "test_file.txt").write_text("test content")
            (cache_dir / "subdir").mkdir()
            (cache_dir / "subdir" / "nested_file.txt").write_text("nested content")
            
            print(f"✅ Created test .cache directory: {cache_dir}")
            print(f"   Contents: {list(cache_dir.rglob('*'))}")
            
            # Create a test database path
            test_db = test_dir / "test.db"
            
            # Initialize the migrator
            migrator = DatabaseMigrator(str(test_db))
            
            # Verify cache directory exists before migration
            assert cache_dir.exists(), "Cache directory should exist before migration"
            print("✅ Cache directory exists before migration")
            
            # Run migrations (which should clean up cache)
            success = migrator.run_migrations()
            
            if success:
                print("✅ Migrations completed successfully")
                
                # Verify cache directory was deleted
                if not cache_dir.exists():
                    print("✅ Cache directory was successfully deleted!")
                    return True
                else:
                    print("❌ Cache directory still exists after migration!")
                    return False
            else:
                print("❌ Migrations failed")
                return False
                
        finally:
            # Restore original directory
            os.chdir(original_cwd)

def test_cache_cleanup_initialize():
    """Test that cache cleanup works during database initialization"""
    print("\n🧪 Testing cache cleanup during database initialization...")
    print("=" * 50)
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = Path(temp_dir)
        
        # Change to test directory
        original_cwd = os.getcwd()
        os.chdir(test_dir)
        
        try:
            # Create a fake .cache directory with some content
            cache_dir = test_dir / ".cache"
            cache_dir.mkdir()
            
            # Add some fake cache files
            (cache_dir / "init_test_file.txt").write_text("init test content")
            
            print(f"✅ Created test .cache directory: {cache_dir}")
            
            # Create a test database path
            test_db = test_dir / "test_init.db"
            
            # Initialize the migrator
            migrator = DatabaseMigrator(str(test_db))
            
            # Verify cache directory exists before initialization
            assert cache_dir.exists(), "Cache directory should exist before initialization"
            print("✅ Cache directory exists before initialization")
            
            # Run database initialization (which should clean up cache)
            success = migrator.initialize_database()
            
            if success:
                print("✅ Database initialization completed successfully")
                
                # Verify cache directory was deleted
                if not cache_dir.exists():
                    print("✅ Cache directory was successfully deleted during initialization!")
                    return True
                else:
                    print("❌ Cache directory still exists after initialization!")
                    return False
            else:
                print("❌ Database initialization failed")
                return False
                
        finally:
            # Restore original directory
            os.chdir(original_cwd)

if __name__ == "__main__":
    print("🚀 Testing .cache directory cleanup functionality")
    print("=" * 60)
    
    # Test migration cleanup
    migration_success = test_cache_cleanup()
    
    # Test initialization cleanup
    init_success = test_cache_cleanup_initialize()
    
    # Summary
    print("\n📊 Test Results:")
    print("=" * 30)
    print(f"Migration cleanup: {'✅ PASS' if migration_success else '❌ FAIL'}")
    print(f"Initialization cleanup: {'✅ PASS' if init_success else '❌ FAIL'}")
    
    if migration_success and init_success:
        print("\n🎉 All tests passed! Cache cleanup is working correctly.")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)
