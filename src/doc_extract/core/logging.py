"""Structured logging configuration with loguru."""

import sys

from loguru import logger

from doc_extract.core.config import settings


def setup_logging(log_level: str | None = None) -> None:
    """Configure structured JSON logging.

    Args:
        log_level: Optional override for log level
    """
    level = log_level or settings.log_level

    # Remove default handler
    logger.remove()

    # Add console handler with JSON formatting for production
    if settings.environment == "production":
        logger.add(
            sys.stdout,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
            level=level,
            serialize=True,  # JSON format
        )
    else:
        # Pretty format for local development
        logger.add(
            sys.stdout,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> | {message}",
            level=level,
            colorize=True,
        )

    # Add file handler (only if we can write to the logs directory)
    try:
        import os

        os.makedirs("logs", exist_ok=True)
        logger.add(
            "logs/app.log",
            rotation="10 MB",
            retention="1 week",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name} | {message}",
            level=level,
            enqueue=True,
        )
    except PermissionError:
        pass  # Skip file logging if no permission


# Export configured logger
__all__ = ["logger", "setup_logging"]
