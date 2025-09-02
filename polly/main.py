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

# Import modular components

# Setup logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/polly.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Create the FastAPI app using the modular web_app component
app = create_app()


def run_app():
    """Run the application"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_app()
