"""Log file for diagnosing problems: %USERPROFILE%\\.spotify_downloader\\logs\\app.log.

The windowed .exe has no console, so warnings and unexpected errors from all threads go
into a small rotating file instead of disappearing.
"""
import logging
import logging.handlers
import sys
import threading

from .config import CONFIG_FILE

LOG_DIR = CONFIG_FILE.parent / "logs"
LOG_FILE = LOG_DIR / "app.log"
_FORMAT = "%(asctime)s %(levelname)-7s %(threadName)s %(name)s: %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_dmd", False) for h in root.handlers):
        return
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8", delay=True,
        )
    except OSError as exc:
        # Without a writable data folder log to stderr only (if there is one).
        handler = logging.StreamHandler()
        print(f"[WARNING] No log file: {exc}", file=sys.stderr)
    handler._dmd = True
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
    # Third-party libraries are chatty at INFO.
    for name in ("urllib3", "spotipy", "pywebview", "requests"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def log_uncaught(exc_type, exc, tb):
        logging.getLogger("uncaught").critical("Unhandled error", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    def log_uncaught_thread(args):
        if args.exc_type is SystemExit:
            return
        logging.getLogger("uncaught").critical(
            "Unhandled error in thread %s", getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_uncaught_thread
