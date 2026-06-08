"""
logger.py - 操作日志
"""

import logging
from pathlib import Path

from .config import load_config, resolve_project_path

_LOGGER: logging.Logger | None = None


def get_log_file() -> Path:
    """获取日志文件绝对路径。"""
    cfg = load_config()
    return resolve_project_path(cfg.get("log_file", "logs/mkcert.log"))


def _get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    log_file = get_log_file()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("mkcert_tool")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    _LOGGER = logger
    return logger


def log_event(action: str, message: str, **details: object) -> None:
    """写入一条操作日志。"""
    detail_text = ""
    if details:
        detail_text = " | " + " | ".join(
            f"{key}={value}" for key, value in details.items()
        )
    _get_logger().info("%s | %s%s", action, message, detail_text)
