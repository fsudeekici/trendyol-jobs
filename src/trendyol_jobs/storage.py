import os
from pathlib import Path

from trendyol_jobs.models import Job


def write_jobs(jobs: list[Job], path: Path) -> None:
    """Write one job per line. The old file is replaced only after the new one is complete."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        for job in jobs:
            file.write(job.model_dump_json() + "\n")
    os.replace(tmp_path, path)


def read_jobs(path: Path) -> list[Job]:
    with Path(path).open(encoding="utf-8") as file:
        return [Job.model_validate_json(line) for line in file if line.strip()]
