import logging
import os

logging.basicConfig(
    level=os.environ.get("ATHENA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def get_logger(name: str = "athena") -> logging.Logger:
    return logging.getLogger(name)
