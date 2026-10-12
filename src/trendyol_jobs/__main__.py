import logging
import sys
from pathlib import Path

from trendyol_jobs.spider import LeverError, run

DEFAULT_PATH = Path("data/jobs.jsonl")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        result = run(DEFAULT_PATH)
    except LeverError as exc:
        logging.getLogger("trendyol_jobs").error("run failed, nothing saved: %s", exc)
        return 1
    return 1 if result.skipped else 0


if __name__ == "__main__":
    sys.exit(main())
