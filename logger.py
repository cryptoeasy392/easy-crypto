import logging


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Set the logging level for httpx to WARNING to suppress informational messages
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)