import logging
import os

def setup_logger(config: dict):
    """Configures system-wide logging using file and console handlers."""
    level_str = config.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    
    log_file = config.get("file", "logs/aether.log")
    
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        
    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding='utf-8')
        ]
    )
    
    logger = logging.getLogger("Aether")
    logger.info("Logger initialized.")
    return logger
