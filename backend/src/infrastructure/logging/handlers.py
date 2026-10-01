"""Rotating file handlers for the ``log`` / ``json`` / ``csv`` exports."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .renderers import CSV_COLUMNS, csv_line


class CsvRotatingFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` that writes the CSV header at the top of every file."""

    def __init__(self, filename: str | Path, **kwargs) -> None:
        kwargs.setdefault("encoding", "utf-8")
        # Append only: the header is written when the file is (still) empty.
        kwargs["mode"] = "a"
        super().__init__(filename, **kwargs)
        self.header = csv_line(CSV_COLUMNS)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            if self.stream is None:
                self.stream = self._open()
            if self.stream.tell() == 0:
                self.stream.write(self.header + self.terminator)
            logging.FileHandler.emit(self, record)
        except Exception:
            self.handleError(record)


def rotating_file_handler(
    path: Path,
    *,
    csv: bool = False,
    max_bytes: int,
    backup_count: int,
) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    cls = CsvRotatingFileHandler if csv else RotatingFileHandler
    return cls(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
        delay=True,
    )
