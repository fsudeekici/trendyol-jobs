import json

from trendyol_jobs.spider import DROPPED_FIELDS, parse_postings
from trendyol_jobs.storage import read_jobs, write_jobs


def test_one_line_per_job_and_reads_back_the_same(raw_postings, tmp_path):
    jobs = parse_postings(raw_postings).jobs
    path = tmp_path / "jobs.jsonl"

    write_jobs(jobs, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 35
    assert [json.loads(line)["id"] for line in lines] == [job.id for job in jobs]
    assert read_jobs(path) == jobs


def test_turkish_letters_are_readable_in_the_file(raw_postings, tmp_path):
    path = tmp_path / "jobs.jsonl"

    write_jobs(parse_postings(raw_postings).jobs, path)

    text = path.read_text(encoding="utf-8")
    assert "İzmir" in text
    assert "Kocaeli / Çayırova" in text


def test_dropped_fields_are_not_in_the_file(raw_postings, tmp_path):
    path = tmp_path / "jobs.jsonl"

    write_jobs(parse_postings(raw_postings).jobs, path)

    for line in path.read_text(encoding="utf-8").splitlines():
        assert not DROPPED_FIELDS & json.loads(line).keys()


def test_writing_again_replaces_the_file(raw_postings, tmp_path):
    jobs = parse_postings(raw_postings).jobs
    path = tmp_path / "jobs.jsonl"

    write_jobs(jobs, path)
    write_jobs(jobs[:3], path)

    assert read_jobs(path) == jobs[:3]
    assert list(tmp_path.iterdir()) == [path]


def test_missing_folder_is_created(raw_postings, tmp_path):
    path = tmp_path / "data" / "jobs.jsonl"

    write_jobs(parse_postings(raw_postings).jobs, path)

    assert len(read_jobs(path)) == 35
