import os
from typing import Optional

from eodms import api_logger


def configure_wrapper_logging(log_file: Optional[str] = None, level: Optional[str] = None) -> str:
    """Apply a consistent logging setup for wrapper scripts."""
    resolved_log_file = log_file or os.path.join(os.path.expanduser('~'), '.eodms', 'eodms.log')
    api_logger.configure_logging(level=level, log_file=resolved_log_file)
    return resolved_log_file
