#!/usr/bin/env python3
"""
Demo script showing .cache directory cleanup during database migrations
"""

from pathlib import Path

def create_demo_cache():
    """Create a demo .cache directory with some files"""
    cache_dir = Path(".cache")
    
    if cache_dir.exists():
        print(f"📁 .cache directory already exists at {cache_dir.absolute()}")
        return cache_dir
    
    # Create cache directory and some demo files
    cache_dir.mkdir()
    
    # Add some demo cache files
    (cache_dir / "user_sessions.json").write_text('{"user_123": "session_data"}')
    (cache_dir / "guild_data.json").write_text('{"guild_456": "cached_guild_info"}')
    (cache_dir / "temp_data").mkdir()
    (cache_dir / "temp_data" / "temp_file.txt").write_text("temporary data")
    
    print(f"✅ Created demo .cache directory at {cache_dir.absolute()}")
    print(f"   Contents: {list(cache_dir.rglob('*'))}")
    
    return cache_dir

def show_cache_status():
    """Show current status of .cache directory"""
    cache_dir = Path(".cache")
    
    if cache_dir.exists():
        files = list(cache_dir.rglob("*"))
        print(f"📁 .cache directory exists with {len(files)} items:")
        for file in files:
            print(f"   - {file.relative_to(cache_dir)}")
    else:
        print("📭 .cache directory does not exist")

if __name__ == "__main__":
    print("🎬 Demonstrating .cache directory cleanup during migrations")
    print("=" * 60)
    
    print("\n1️⃣ Current cache status:")
    show_cache_status()
    
    print("\n2️⃣ Creating demo .cache directory:")
    create_demo_cache()
    
    print("\n3️⃣ Cache status after creation:")
    show_cache_status()
    
    print("\n4️⃣ Now run a database migration and the .cache directory will be automatically deleted!")
    print("   You can test this by running:")
    print("   - uv run python run_migration.py")
    print("   - uv run python migrate_database.py") 
    print("   - uv run python polly/migrations.py")
    print("   - Or just start the application (migrations run on startup)")
    
    print("\n💡 The cache cleanup happens in polly/migrations.py in the _cleanup_cache_directory() method")
    print("   This ensures fresh cache state after any database schema changes.")
