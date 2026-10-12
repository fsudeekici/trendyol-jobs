import logging
from datetime import datetime, timedelta, timezone

from trendyol_jobs.models import Job, SalaryRange
from trendyol_jobs.spider import (
    DROPPED_FIELDS,
    KEPT_FIELDS,
    find_personal_data,
    parse_posting,
    parse_postings,
)

TYPICAL_ID = "26dd93ee-ae0f-4864-9f1e-9b66ad7e857a"
EMPTY_ID = "a990f27e-eafd-4301-921c-0a6961531c22"
SALARY_ID = "7c0434d6-14cd-4c67-838e-39081af21e65"
SALARY_DESCRIPTION_ID = "b9429d9d-4531-4a07-b119-476a293381ef"
TWO_LOCATIONS_ID = "47543835-3fce-4ca8-802f-76b82a943cc7"
EMPTY_HEADING_ID = "ab242d73-bfbf-4b93-adc4-d54c776c69a4"
IZMIR_ID = "56cf5f7e-43f8-49bd-bfaf-2168f1209850"
CAYIROVA_ID = "e11c5931-6f4c-4086-b0ed-0b98c9abd2eb"

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# --- all real postings ---


def test_all_real_postings_parse(raw_postings):
    result = parse_postings(raw_postings)

    assert len(raw_postings) == 35
    assert len(result.jobs) == 35
    assert result.skipped == []
    assert [job.id for job in result.jobs] == [raw["id"] for raw in raw_postings]


def test_every_kept_field_matches_the_real_data(raw_postings):
    for raw in raw_postings:
        job = parse_posting(raw)
        categories = raw["categories"]

        assert job.id == raw["id"]
        assert job.title == raw["text"]
        assert job.commitment == categories["commitment"]
        assert job.department == categories["department"]
        assert job.team == categories["team"]
        assert job.location == categories["location"]
        assert job.all_locations == categories["allLocations"]
        assert job.country == raw["country"]
        assert job.workplace_type == raw["workplaceType"]
        assert job.created_at == EPOCH + timedelta(milliseconds=raw["createdAt"])
        assert job.url == raw["hostedUrl"]
        assert job.description_html == raw["description"]
        assert job.opening_html == raw["opening"]
        assert job.description_body_html == raw["descriptionBody"]
        assert job.additional_html == raw["additional"]
        assert [(item.heading, item.content_html) for item in job.lists] == [
            (item["text"], item["content"]) for item in raw["lists"]
        ]
        if "salaryRange" in raw:
            assert job.salary_range.model_dump() == raw["salaryRange"]
        else:
            assert job.salary_range is None
        assert job.salary_description_html == raw.get("salaryDescription")


def test_only_the_approved_fields_are_dropped(raw_postings):
    assert DROPPED_FIELDS == {
        "applyUrl",
        "descriptionPlain",
        "openingPlain",
        "descriptionBodyPlain",
        "additionalPlain",
        "salaryDescriptionPlain",
    }
    seen = {key for raw in raw_postings for key in raw}
    assert seen == KEPT_FIELDS | DROPPED_FIELDS
    assert not KEPT_FIELDS & DROPPED_FIELDS


def test_real_data_has_no_unknown_fields(raw_postings, caplog):
    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        parse_postings(raw_postings)

    assert "unknown field" not in caplog.text.lower()


def test_real_data_has_no_personal_data(raw_postings):
    for raw in raw_postings:
        assert find_personal_data(parse_posting(raw)) == []


# --- known postings ---


def test_typical_posting(raw_by_id):
    job = parse_posting(raw_by_id[TYPICAL_ID])

    assert isinstance(job, Job)
    assert job.title == "Account Senior Specialist - A Brands"
    assert job.commitment == "Full-time"
    assert job.department == "Core Commerce"
    assert job.team == "Gulf Category"
    assert job.location == "Riyadh"
    assert job.all_locations == ["Riyadh"]
    assert job.country == "SA"
    assert job.workplace_type == "hybrid"
    assert job.created_at == datetime(2026, 10, 11, 14, 19, 42, 323000, tzinfo=timezone.utc)
    assert job.url == "https://jobs.lever.co/trendyol/26dd93ee-ae0f-4864-9f1e-9b66ad7e857a"
    assert [item.heading for item in job.lists] == ["Key Responsibilities", "Requirements"]
    assert job.opening_html.startswith('<div><b><span style="font-size: 18px">About the Team</span>')
    assert job.description_body_html.startswith('<div><strong><span data-sheets-root="1">About the Role</span>')
    assert job.additional_html.startswith('<div><b><span style="font-size: 18px">What We Offer</span></b></div>')
    assert job.salary_range is None
    assert job.salary_description_html is None


def test_posting_with_no_text_is_kept_and_logged(raw_postings, caplog):
    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        result = parse_postings(raw_postings)

    job = next(job for job in result.jobs if job.id == EMPTY_ID)
    assert job.title == "FMCG & Cosmetics Manager"
    assert job.description_html == ""
    assert job.lists == []
    assert job.additional_html == ""
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and EMPTY_ID in r.getMessage()]
    assert len(warnings) == 1
    assert "no text" in warnings[0].getMessage()


def test_zero_salary_range_is_stored_as_it_is(raw_by_id):
    job = parse_posting(raw_by_id[SALARY_ID])

    assert job.salary_range == SalaryRange(min=0, max=0, currency="SAR", interval="per-month-salary")
    assert job.salary_range.model_dump() == {
        "min": 0,
        "max": 0,
        "currency": "SAR",
        "interval": "per-month-salary",
    }


def test_salary_description_is_kept(raw_by_id):
    job = parse_posting(raw_by_id[SALARY_DESCRIPTION_ID])

    assert job.title == "Seller Acquisition Intern"
    assert job.salary_description_html.startswith("<div>\n<p><strong>Your Main Responsibilities</strong>")


def test_posting_with_two_locations(raw_by_id):
    job = parse_posting(raw_by_id[TWO_LOCATIONS_ID])

    assert job.location == "Berlin"
    assert job.all_locations == ["Berlin", "Brussels"]


def test_empty_list_heading_is_kept(raw_by_id):
    job = parse_posting(raw_by_id[EMPTY_HEADING_ID])

    assert len(job.lists) == 1
    assert job.lists[0].heading == ""
    assert job.lists[0].content_html.startswith("<div><strong>Responsibilities</strong></div>")


def test_turkish_letters_are_kept(raw_by_id):
    assert parse_posting(raw_by_id[IZMIR_ID]).location == "İzmir"
    assert parse_posting(raw_by_id[IZMIR_ID]).title == (
        "Trendyol Express - Dağıtım Merkezi Operasyon Yöneticisi (İzmir)"
    )
    assert parse_posting(raw_by_id[CAYIROVA_ID]).location == "Kocaeli / Çayırova"


# --- things the real data does not have yet ---
# Each test starts from a real posting and changes one thing.


def test_new_field_from_lever_is_logged(real_posting, caplog):
    raw = real_posting(TYPICAL_ID)
    raw["remoteAllowed"] = True

    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        result = parse_postings([raw])

    assert len(result.jobs) == 1
    assert result.skipped == []
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("unknown field" in m and "remoteAllowed" in m and TYPICAL_ID in m for m in messages)


def test_new_nested_field_from_lever_is_logged(real_posting, caplog):
    raw = real_posting(TYPICAL_ID)
    raw["categories"]["level"] = "Senior"

    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        parse_postings([raw])

    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("unknown field" in m and "categories.level" in m and TYPICAL_ID in m for m in messages)


def test_missing_optional_field_is_logged_and_posting_is_kept(real_posting, caplog):
    raw = real_posting(TYPICAL_ID)
    del raw["workplaceType"]
    del raw["categories"]["team"]

    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        result = parse_postings([raw])

    assert result.skipped == []
    assert result.jobs[0].workplace_type is None
    assert result.jobs[0].team is None
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("missing field workplaceType" in m and TYPICAL_ID in m for m in messages)
    assert any("missing field categories.team" in m and TYPICAL_ID in m for m in messages)


def test_real_data_has_no_missing_fields(raw_postings, caplog):
    with caplog.at_level(logging.WARNING, logger="trendyol_jobs"):
        parse_postings(raw_postings)

    assert "missing field" not in caplog.text


def test_broken_posting_is_logged_and_counted(real_posting, caplog):
    broken = real_posting(TYPICAL_ID)
    del broken["text"]
    good = real_posting(SALARY_ID)

    with caplog.at_level(logging.ERROR, logger="trendyol_jobs"):
        result = parse_postings([broken, good])

    assert [job.id for job in result.jobs] == [SALARY_ID]
    assert len(result.skipped) == 1
    assert result.skipped[0].id == TYPICAL_ID
    assert "text" in result.skipped[0].reason
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any(TYPICAL_ID in m for m in errors)


def test_posting_that_is_not_an_object_is_logged_and_counted(real_posting, caplog):
    with caplog.at_level(logging.ERROR, logger="trendyol_jobs"):
        result = parse_postings(["not a posting", real_posting(SALARY_ID)])

    assert [job.id for job in result.jobs] == [SALARY_ID]
    assert len(result.skipped) == 1
    assert result.skipped[0].id is None
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 1


def test_posting_with_an_email_is_skipped_and_logged(real_posting, caplog):
    raw = real_posting(TYPICAL_ID)
    raw["additional"] += '<div>Questions? Write to <a href="mailto:jane.doe@example.com">Jane</a></div>'

    with caplog.at_level(logging.ERROR, logger="trendyol_jobs"):
        result = parse_postings([raw, real_posting(SALARY_ID)])

    assert [job.id for job in result.jobs] == [SALARY_ID]
    assert len(result.skipped) == 1
    assert result.skipped[0].id == TYPICAL_ID
    assert "email" in result.skipped[0].reason
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any(TYPICAL_ID in m and "email" in m for m in errors)
    # the personal data itself must not be copied into the log
    assert "jane.doe@example.com" not in caplog.text
    assert "jane.doe@example.com" not in result.skipped[0].reason


def test_posting_with_a_phone_number_is_skipped(real_posting):
    raw = real_posting(TYPICAL_ID)
    raw["lists"][0]["content"] += "<div>Call +90 555 123 45 67</div>"

    result = parse_postings([raw])

    assert result.jobs == []
    assert result.skipped[0].id == TYPICAL_ID
    assert "phone" in result.skipped[0].reason


def test_posting_with_a_linkedin_profile_is_skipped(real_posting):
    raw = real_posting(TYPICAL_ID)
    raw["description"] += '<a href="https://www.linkedin.com/in/jane-doe">Recruiter</a>'

    result = parse_postings([raw])

    assert result.jobs == []
    assert result.skipped[0].id == TYPICAL_ID
    assert "linkedin" in result.skipped[0].reason.lower()
