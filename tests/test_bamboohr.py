import json
from unittest.mock import MagicMock, patch

import pytest


def _mock_response(result, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status != 200:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    resp.json.return_value = {"result": result}
    return resp


def _make_job(
    job_id="123",
    name="Solutions Engineer",
    city="Boston",
    state="Massachusetts",
    is_remote=None,
):
    return {
        "id": job_id,
        "jobOpeningName": name,
        "location": {"city": city, "state": state},
        "isRemote": is_remote,
    }


class TestFetchJobs:
    def test_returns_job_listing_objects(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([_make_job()])):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert "123" in results[0].url
        assert geo == 0

    def test_job_url_uses_slug_and_id(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([_make_job(job_id="456")])):
            results, _ = fetch_jobs("mycompany")
        assert results[0].url == "https://mycompany.bamboohr.com/careers/456"

    def test_location_city_state(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([_make_job(city="Austin", state="Texas")])):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "Austin, Texas"

    def test_remote_flag_sets_remote_location(self):
        from scrapers.bamboohr import fetch_jobs
        job = _make_job(is_remote=True, city="", state="")
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([job])):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "Remote"

    def test_geo_filter_excludes_non_us(self):
        from scrapers.bamboohr import fetch_jobs
        job = _make_job(city="Chennai", state="Tamil Nadu")
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([job])):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_title_geo_filter_excludes_emea(self):
        from scrapers.bamboohr import fetch_jobs
        job = _make_job(name="Solutions Engineer - EMEA", city="Boston", state="MA")
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([job])):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_http_error_returns_empty(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", side_effect=Exception("connection refused")):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_http_status_error_returns_empty(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([], status=403)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_name_skipped(self):
        from scrapers.bamboohr import fetch_jobs
        jobs = [
            {"id": "1", "jobOpeningName": "", "location": {"city": "NY", "state": "New York"}, "isRemote": None},
            _make_job(job_id="2"),
        ]
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response(jobs)):
            results, _ = fetch_jobs("acme")
        assert len(results) == 1

    def test_missing_id_skipped(self):
        from scrapers.bamboohr import fetch_jobs
        jobs = [
            {"id": "", "jobOpeningName": "Engineer", "location": {"city": "NY", "state": "NY"}, "isRemote": None},
            _make_job(job_id="99"),
        ]
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response(jobs)):
            results, _ = fetch_jobs("acme")
        assert len(results) == 1

    def test_empty_result_returns_empty(self):
        from scrapers.bamboohr import fetch_jobs
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([])):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_multiple_jobs_returned(self):
        from scrapers.bamboohr import fetch_jobs
        jobs = [_make_job(job_id=str(i)) for i in range(3)]
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response(jobs)):
            results, _ = fetch_jobs("acme")
        assert len(results) == 3

    def test_city_only_location(self):
        from scrapers.bamboohr import fetch_jobs
        job = _make_job(city="Portland", state="")
        with patch("scrapers.bamboohr.requests.get", return_value=_mock_response([job])):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "Portland"
