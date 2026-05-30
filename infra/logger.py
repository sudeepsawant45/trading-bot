# ============================================================
# infra/logger.py — Logging Setup
# ============================================================
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from infra.config import LOG_DIR

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    log_file = LOG_DIR / f"trading_{datetime.now().strftime('%Y%m%d')}.log"
    fh = RotatingFileHandler(str(log_file), maxBytes=10*1024*1024, backupCount=30)
    fh.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                             datefmt="%Y-%m-%d %H:%M:%S")
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    try:
        import colorlog
        cfmt = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s | %(message)s%(reset)s",
            datefmt="%H:%M:%S",
            log_colors={"DEBUG":"cyan","INFO":"green","WARNING":"yellow",
                        "ERROR":"red","CRITICAL":"red,bg_white"})
        ch.setFormatter(cfmt)
    except ImportError:
        ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger
