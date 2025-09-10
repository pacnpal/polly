"""
Polly Main Application Entry Point
Streamlined entry point that imports functionality from modular components.
"""

from .web_app import create_app
import os
import logging
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Import debug configuration and initialize it early
from .debug_config import init_debug_config, get_debug_logger

# Setup logging directories
os.makedirs("logs", exist_ok=True)

# Configure basic logging structure (level will be set by debug config)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/polly.log"), logging.StreamHandler()],
)

# Initialize debug configuration (this will set appropriate log levels)
init_debug_config()

# Get debug-aware logger
logger = get_debug_logger(__name__)

# Create the FastAPI app using the modular web_app component
app = create_app()


def run_app():
    """Run the application"""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_app()
