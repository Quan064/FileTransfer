import logging
import sys
import os

LOG_DIR = 'logs'
LOG_FILE = os.path.join(LOG_DIR, 'server.log')

def setup_server_logger(name: str = 'FileServer', level=logging.INFO) -> logging.Logger:
    """Sets up a logger that outputs to both a file and the console."""
    # Create log directory if it doesn't exist
    os.makedirs(LOG_DIR, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding multiple handlers if the function is called more than once
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Log to file
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Log to console
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    
    return logger