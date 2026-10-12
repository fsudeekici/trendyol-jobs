from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Model(BaseModel):
    # strict: never change a value's type quietly. forbid: never accept a field we do not know.
    model_config = ConfigDict(strict=True, extra="forbid")


class SalaryRange(_Model):
    min: int | float | None = None
    max: int | float | None = None
    currency: str | None = None
    interval: str | None = None


class JobList(_Model):
    heading: str
    content_html: str


class Job(_Model):
    """One Trendyol job. A field Lever did not send is None."""

    id: str
    title: str
    department: str | None
    team: str | None
    commitment: str | None
    location: str | None
    all_locations: list[str]
    country: str | None
    workplace_type: str | None
    created_at: datetime
    url: str
    description_html: str | None
    opening_html: str | None
    description_body_html: str | None
    lists: list[JobList]
    additional_html: str | None
    salary_range: SalaryRange | None
    salary_description_html: str | None
