import copy
import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "lever_trendyol_2026-10-12.json"


@pytest.fixture(scope="session")
def fixture_bytes() -> bytes:
    """The real Lever response, exactly as saved."""
    return FIXTURE.read_bytes()


@pytest.fixture
def raw_postings(fixture_bytes) -> list[dict]:
    return json.loads(fixture_bytes)


@pytest.fixture
def raw_by_id(raw_postings) -> dict[str, dict]:
    return {raw["id"]: raw for raw in raw_postings}


@pytest.fixture
def real_posting(raw_by_id):
    """Give a fresh copy of one real posting, safe to change in a test."""

    def _get(posting_id: str) -> dict:
        return copy.deepcopy(raw_by_id[posting_id])

    return _get
