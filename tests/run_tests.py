"""
Test runner for Polly comprehensive test suite.
Runs all tests with proper configuration and reporting.
"""

import sys
import os
import subprocess
from pathlib import Path

def main():
    """Run the comprehensive test suite."""
    
    # Add the project root to Python path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Set environment variables for testing
    os.environ.setdefault("TESTING", "1")
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("DISCORD_TOKEN", "test_token")
    
    # Test configuration
    test_args = [
        "python", "-m", "pytest",
        str(Path(__file__).parent),  # tests directory
        "-v",  # verbose output
        "--tb=short",  # shorter traceback format
        "--strict-markers",  # strict marker checking
        "--disable-warnings",  # disable warnings for cleaner output
        "-x",  # stop on first failure (remove for full run)
        "--maxfail=10",  # stop after 10 failures
        "--durations=10",  # show 10 slowest tests
        "-p", "no:cacheprovider",  # disable cache for clean runs
    ]
    
    # Add coverage if available
    try:
        import coverage
        test_args.extend([
            "--cov=polly",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "--cov-fail-under=80"
        ])
        print("Running tests with coverage...")
    except ImportError:
        print("Running tests without coverage (install pytest-cov for coverage)...")
    
    # Run specific test categories
    if len(sys.argv) > 1:
        category = sys.argv[1].lower()
        
        if category == "unit":
            test_args.extend([
                "test_database.py",
                "test_validators.py",
                "test_emoji_handler.py"
            ])
            print("Running unit tests...")
            
        elif category == "integration":
            test_args.extend([
                "test_web_app.py",
                "test_discord_bot.py",
                "test_background_tasks.py",
                "test_integration.py"
            ])
            print("Running integration tests...")
            
        elif category == "fast":
            test_args.extend([
                "-m", "not slow",  # Skip slow tests
                "test_database.py",
                "test_validators.py"
            ])
            print("Running fast tests...")
            
        elif category == "security":
            test_args.extend([
                "-k", "security or malicious or edge_case",
            ])
            print("Running security tests...")
            
        else:
            print(f"Unknown category: {category}")
            print("Available categories: unit, integration, fast, security")
            return 1
    else:
        print("Running all tests...")
    
    # Run the tests
    try:
        result = subprocess.run(test_args, cwd=project_root)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 130
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
