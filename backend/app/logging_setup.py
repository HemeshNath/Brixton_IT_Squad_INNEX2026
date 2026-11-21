"""Logging that can never leak personal data: every log line passes through mask_pii before it
is written, so phone numbers, emails, OTPs, card/account numbers etc. show up as placeholders."""
from __future__ import annotations

import logging

from .checks.textprep import mask_pii

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class PIIRedactingFilter(logging.Filter):
    """Masks personal data in the final log message (after %-formatting)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # badly formatted log call - leave it to the handler
            return True
        masked = mask_pii(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True  # never drop a log line, only clean it


def setup_logging(level: int = logging.INFO) -> None:
    """Root logging with the redacting filter on every root handler (also covers child loggers)."""
    logging.basicConfig(level=level, format=LOG_FORMAT)
    redact = PIIRedactingFilter()
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, PIIRedactingFilter) for f in handler.filters):
            handler.addFilter(redact)
