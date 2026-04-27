import logging
from collections.abc import Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SensitiveDataFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(secret for secret in secrets if secret)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            redacted = redacted.replace(secret, "***REDACTED***")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


class ServiceContextFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service_name
        return True


def configure_logging(
    level: str,
    secrets: Iterable[str],
    *,
    service_name: str,
    log_directory: Path,
) -> None:
    root_logger = logging.getLogger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(service)s] %(name)s %(message)s",
    )

    root_logger.handlers.clear()
    root_logger.setLevel(log_level)

    log_directory.mkdir(parents=True, exist_ok=True)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(ServiceContextFilter(service_name))
    console_handler.addFilter(SensitiveDataFilter(secrets))

    file_handler = RotatingFileHandler(
        log_directory / f"{service_name}.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(ServiceContextFilter(service_name))
    file_handler.addFilter(SensitiveDataFilter(secrets))

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
