import json
import logging

import httpx
import pytest

from trendyol_jobs.spider import POSTINGS_URL, LeverError, fetch_postings, run
from trendyol_jobs.storage import read_jobs


def client_returning(status_code: int, content: bytes, content_type: str = "application/json; charset=utf-8"):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status_code, content=content, headers={"Content-Type": content_type})

    return httpx.Client(transport=httpx.MockTransport(handler)), requests


def test_fetch_returns_every_posting(fixture_bytes, raw_postings):
    client, requests = client_returning(200, fixture_bytes)

    postings = fetch_postings(client)

    assert postings == raw_postings
    assert len(requests) == 1
    assert str(requests[0].url) == POSTINGS_URL
    assert POSTINGS_URL == "https://api.lever.co/v0/postings/trendyol?mode=json"


def test_fetch_raises_on_404():
    # the real body Lever sends for an unknown site
    client, _ = client_returning(404, b'{"ok":false,"error":"Document not found"}')

    with pytest.raises(LeverError, match="404"):
        fetch_postings(client)


def test_fetch_raises_on_reply_that_is_not_json():
    client, _ = client_returning(200, b"<html><body>Service unavailable</body></html>", "text/html")

    with pytest.raises(LeverError, match="JSON"):
        fetch_postings(client)


def test_fetch_raises_when_reply_is_not_a_list():
    client, _ = client_returning(200, b'{"ok":false,"error":"Document not found"}')

    with pytest.raises(LeverError, match="list"):
        fetch_postings(client)


def test_run_saves_every_real_job(fixture_bytes, raw_postings, tmp_path, caplog):
    client, _ = client_returning(200, fixture_bytes)
    path = tmp_path / "data" / "jobs.jsonl"

    with caplog.at_level(logging.INFO, logger="trendyol_jobs"):
        result = run(path, client=client)

    assert len(result.jobs) == 35
    assert result.skipped == []
    assert read_jobs(path) == result.jobs
    assert "35 fetched, 35 saved, 0 skipped" in caplog.text


def test_run_counts_skipped_postings(raw_postings, tmp_path, caplog):
    del raw_postings[0]["id"]
    client, _ = client_returning(200, json.dumps(raw_postings).encode())
    path = tmp_path / "jobs.jsonl"

    with caplog.at_level(logging.INFO, logger="trendyol_jobs"):
        result = run(path, client=client)

    assert len(result.jobs) == 34
    assert len(result.skipped) == 1
    assert len(read_jobs(path)) == 34
    assert "35 fetched, 34 saved, 1 skipped" in caplog.text


def test_run_keeps_the_old_file_when_fetch_fails(fixture_bytes, tmp_path):
    path = tmp_path / "jobs.jsonl"
    good_client, _ = client_returning(200, fixture_bytes)
    run(path, client=good_client)
    before = path.read_bytes()
    bad_client, _ = client_returning(404, b'{"ok":false,"error":"Document not found"}')

    with pytest.raises(LeverError):
        run(path, client=bad_client)

    assert path.read_bytes() == before


def test_fetch_raises_on_empty_list():
    client, _ = client_returning(200, b"[]")

    with pytest.raises(LeverError, match="0 postings"):
        fetch_postings(client)


def test_run_raises_on_empty_reply_and_keeps_the_old_file(fixture_bytes, tmp_path):
    path = tmp_path / "jobs.jsonl"
    good_client, _ = client_returning(200, fixture_bytes)
    run(path, client=good_client)
    before = path.read_bytes()
    empty_client, _ = client_returning(200, b"[]")

    with pytest.raises(LeverError, match="0 postings"):
        run(path, client=empty_client)

    assert path.read_bytes() == before
    assert len(read_jobs(path)) == 35


def test_run_on_empty_reply_does_not_create_a_file(tmp_path):
    path = tmp_path / "jobs.jsonl"
    empty_client, _ = client_returning(200, b"[]")

    with pytest.raises(LeverError, match="0 postings"):
        run(path, client=empty_client)

    assert list(tmp_path.iterdir()) == []
