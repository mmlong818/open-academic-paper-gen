"""Mask secrets in log lines: OpenAlex takes its key as a URL parameter, and httpx logs every URL."""
import logging
import re

_KEY_PARAM = re.compile(r"((?:api_key|apikey|access_token)=)[^&\s\"']+", re.IGNORECASE)


class RedactSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = _KEY_PARAM.sub(r"\1***", message)
        if masked != message:
            record.msg, record.args = masked, None
        return True
