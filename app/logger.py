from __future__ import annotations

import logging
from pathlib import Path


class AppLogger:
    """Factory de logger reutilisable pour l'application."""

    _configured_keys: set[str] = set()

    @classmethod
    def get_logger(
        cls,
        name: str,
        *,
        log_file: str = "app.log",
        level: int = logging.INFO,
    ) -> logging.Logger:
        logger = logging.getLogger(name)
        config_key = f"{name}:{log_file}"

        if config_key in cls._configured_keys:
            return logger

        log_dir = Path(__file__).resolve().parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_file

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )

        logger.setLevel(level)
        logger.addHandler(file_handler)
        logger.propagate = False

        cls._configured_keys.add(config_key)
        return logger
