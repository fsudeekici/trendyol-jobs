import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from pydantic import ValidationError

from trendyol_jobs.models import Job, JobList, SalaryRange
from trendyol_jobs.storage import write_jobs

logger = logging.getLogger("trendyol_jobs")

POSTINGS_URL = "https://api.lever.co/v0/postings/trendyol?mode=json"

REQUIRED_FIELDS = ("id", "text", "categories", "createdAt", "hostedUrl")
KEPT_FIELDS = frozenset(
    {
        *REQUIRED_FIELDS,
        "country",
        "workplaceType",
        "description",
        "opening",
        "descriptionBody",
        "lists",
        "additional",
        "salaryRange",
        "salaryDescription",
    }
)
# Dropped on purpose: copies of kept fields. See the field table in the plan.
DROPPED_FIELDS = frozenset(
    {
        "applyUrl",
        "descriptionPlain",
        "openingPlain",
        "descriptionBodyPlain",
        "additionalPlain",
        "salaryDescriptionPlain",
    }
)
# Not always sent by Lever, so their absence is normal.
RARE_FIELDS = frozenset({"salaryRange", "salaryDescription", "salaryDescriptionPlain"})
CATEGORY_FIELDS = frozenset({"commitment", "department", "team", "location", "allLocations"})
LIST_FIELDS = frozenset({"text", "content"})
SALARY_RANGE_FIELDS = frozenset({"min", "max", "currency", "interval"})

PERSONAL_DATA_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone number": re.compile(r"\+?\d[\d ()-]{9,}\d"),
    "LinkedIn profile": re.compile(r"linkedin\.com/in/", re.IGNORECASE),
}

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class LeverError(Exception):
    """The Lever API did not give a usable list of postings."""


class PostingError(ValueError):
    """One posting cannot be turned into a Job."""


@dataclass(frozen=True)
class Skipped:
    id: str | None
    reason: str


@dataclass
class ParseResult:
    jobs: list[Job] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)


def fetch_postings(client: httpx.Client) -> list:
    try:
        response = client.get(POSTINGS_URL)
    except httpx.HTTPError as exc:
        raise LeverError(f"request to Lever failed: {exc}") from exc
    if response.status_code != 200:
        raise LeverError(f"Lever returned HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise LeverError("Lever reply is not JSON") from exc
    if not isinstance(data, list):
        raise LeverError("Lever reply is not a list of postings")
    if not data:
        # Trendyol always has open jobs, so an empty reply is a fault, not news.
        raise LeverError("Lever returned 0 postings")
    return data


def parse_posting(raw: dict) -> Job:
    if not isinstance(raw, dict):
        raise PostingError("posting is not an object")
    missing = [name for name in REQUIRED_FIELDS if name not in raw]
    if missing:
        raise PostingError(f"missing required field: {', '.join(missing)}")
    categories = raw["categories"]
    if not isinstance(categories, dict):
        raise PostingError("categories is not an object")
    created_at = raw["createdAt"]
    if not isinstance(created_at, int) or isinstance(created_at, bool):
        raise PostingError("createdAt is not a whole number")
    lists = raw.get("lists", [])
    if not isinstance(lists, list) or not all(isinstance(item, dict) for item in lists):
        raise PostingError("lists is not a list of objects")
    salary_range = raw.get("salaryRange")
    if salary_range is not None and not isinstance(salary_range, dict):
        raise PostingError("salaryRange is not an object")

    try:
        return Job(
            id=raw["id"],
            title=raw["text"],
            department=categories.get("department"),
            team=categories.get("team"),
            commitment=categories.get("commitment"),
            location=categories.get("location"),
            all_locations=categories.get("allLocations", []),
            country=raw.get("country"),
            workplace_type=raw.get("workplaceType"),
            created_at=EPOCH + timedelta(milliseconds=created_at),
            url=raw["hostedUrl"],
            description_html=raw.get("description"),
            opening_html=raw.get("opening"),
            description_body_html=raw.get("descriptionBody"),
            lists=[
                JobList(heading=item.get("text"), content_html=item.get("content")) for item in lists
            ],
            additional_html=raw.get("additional"),
            salary_range=None if salary_range is None else SalaryRange(**salary_range),
            salary_description_html=raw.get("salaryDescription"),
        )
    except ValidationError as exc:
        # field names and messages only: the bad values could hold personal data
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        raise PostingError(f"invalid posting: {problems}") from exc


def find_personal_data(job: Job) -> list[str]:
    """Return the kinds of personal data found in the job's text, not the data itself."""
    texts = [
        job.title,
        job.description_html,
        job.opening_html,
        job.description_body_html,
        job.additional_html,
        job.salary_description_html,
    ]
    for item in job.lists:
        texts += [item.heading, item.content_html]
    text = "\n".join(t for t in texts if t)
    return [kind for kind, pattern in PERSONAL_DATA_PATTERNS.items() if pattern.search(text)]


def _field_changes(raw: dict) -> tuple[list[str], list[str]]:
    """Return (unknown fields, missing fields) for a posting, using dotted names."""
    unknown = sorted(raw.keys() - KEPT_FIELDS - DROPPED_FIELDS)
    missing = sorted((KEPT_FIELDS | DROPPED_FIELDS) - RARE_FIELDS - raw.keys())

    categories = raw.get("categories")
    if isinstance(categories, dict):
        unknown += sorted(f"categories.{key}" for key in categories.keys() - CATEGORY_FIELDS)
        missing += sorted(f"categories.{key}" for key in CATEGORY_FIELDS - categories.keys())
    salary_range = raw.get("salaryRange")
    if isinstance(salary_range, dict):
        unknown += sorted(f"salaryRange.{key}" for key in salary_range.keys() - SALARY_RANGE_FIELDS)
        missing += sorted(f"salaryRange.{key}" for key in SALARY_RANGE_FIELDS - salary_range.keys())
    lists = raw.get("lists")
    if isinstance(lists, list):
        items = [item for item in lists if isinstance(item, dict)]
        unknown += sorted({f"lists[].{key}" for item in items for key in item.keys() - LIST_FIELDS})
        missing += sorted({f"lists[].{key}" for item in items for key in LIST_FIELDS - item.keys()})
    return unknown, missing


def parse_postings(raws: list) -> ParseResult:
    """Turn raw postings into jobs. Every posting ends up in jobs or in skipped."""
    result = ParseResult()
    for raw in raws:
        posting_id = raw.get("id") if isinstance(raw, dict) else None
        if not isinstance(posting_id, str):
            posting_id = None

        try:
            job = parse_posting(raw)
        except PostingError as exc:
            logger.error("skipped posting %s: %s", posting_id, exc)
            result.skipped.append(Skipped(posting_id, str(exc)))
            continue

        found = find_personal_data(job)
        if found:
            reason = f"personal data found: {', '.join(found)}"
            logger.error("skipped posting %s: %s", job.id, reason)
            result.skipped.append(Skipped(job.id, reason))
            continue

        unknown, missing = _field_changes(raw)
        for name in unknown:
            logger.warning("posting %s: unknown field %s was not saved", job.id, name)
        for name in missing:
            logger.warning("posting %s: missing field %s", job.id, name)
        if not (job.description_html or job.lists or job.additional_html):
            logger.warning("posting %s: no text (no description, lists or additional)", job.id)

        result.jobs.append(job)
    return result


def run(path: Path, client: httpx.Client | None = None) -> ParseResult:
    """Fetch the postings, save the clean jobs to path, and log a summary."""
    if client is None:
        with httpx.Client(timeout=30) as own_client:
            return run(path, own_client)

    raws = fetch_postings(client)
    result = parse_postings(raws)
    write_jobs(result.jobs, path)
    logger.info(
        "%d fetched, %d saved, %d skipped -> %s",
        len(raws),
        len(result.jobs),
        len(result.skipped),
        path,
    )
    return result
