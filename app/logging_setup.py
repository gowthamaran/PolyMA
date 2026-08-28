from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    Path("logs").mkdir(exist_ok=True)
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(level.upper())
    formatter = JsonFormatter()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    for name, filename in (("polyma", "app.log"), ("polyma.scanner", "scanner.log"), ("polyma.errors", "errors.log")):
        handler = RotatingFileHandler(Path("logs") / filename, maxBytes=5_000_000, backupCount=3)
        handler.setFormatter(formatter)
        logging.getLogger(name).addHandler(handler)

