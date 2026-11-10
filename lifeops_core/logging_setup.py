import logging
import os


def configure_logging(level: str | None = None) -> None:
    """Configure root logging once per process.

    Plain single-line format is intentional: local-first stack, logs go to
    stdout and Docker captures them; JSON log shipping arrives later if ever
    needed.
    """
    lvl = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        force=False,
    )
    # Quiet noisy libs without muting errors.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("minio").setLevel(logging.WARNING)
