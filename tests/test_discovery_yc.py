import html as html_mod
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_page_data(jobs):
    return json.dumps({"props": {"jobs": jobs}})


def _make_html(jobs):
    escaped = html_mod.escape(_make_page_data(jobs))
    return f'<html><body><div data-page="{escaped}"></div></body></html>'


def _make_job(
    job_id=1001,
    title="Solutions Engineer",
    company_name="Acme",
    company_slug="acme",
    location="San Francisco, CA, US",
):
    return {
        "id": job_id,
        "title": title,
        "companyName": company_name,
        "companySlug": company_slug,
        "location": location,
    }


def _mock_response(html, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status != 200:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    resp.text = html
    return resp


class TestFetchListings:
    def test_returns_discovery_listing_objects(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job()])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert results[0].company_name == "Acme"
        assert results[0].ats == "YC"
        assert results[0].slug == "acme"
        assert geo == 0

    def test_job_url_uses_id(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(job_id=9999)])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert results[0].url == "https://www.workatastartup.com/jobs/9999"

    def test_location_strips_us_suffix(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="Boston, MA, US")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert results[0].location == "Boston, MA"

    def test_location_takes_first_segment(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="Austin, TX, US / Remote (Austin, TX, US)")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert results[0].location == "Austin, TX"

    def test_remote_location_preserved(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="Remote")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert results[0].location == "Remote"
        assert len(results) == 1

    def test_geo_filter_excludes_non_us(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="London, UK")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 1

    def test_geo_filter_excludes_non_us_country_code(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="Munich, BY, DE")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 1

    def test_us_country_code_accepted(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(location="Austin, TX, US")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert len(results) == 1
        assert geo == 0

    def test_title_geo_filter_excludes_emea(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([_make_job(title="Solutions Engineer - EMEA")])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 1

    def test_http_error_returns_empty(self):
        from scrapers.discovery_yc import fetch_listings
        with patch("scrapers.discovery_yc.requests.get", side_effect=Exception("timeout")):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 0

    def test_http_status_error_returns_empty(self):
        from scrapers.discovery_yc import fetch_listings
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response("", status=403)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 0

    def test_missing_data_page_returns_empty(self):
        from scrapers.discovery_yc import fetch_listings
        html = "<html><body>No data here</body></html>"
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 0

    def test_missing_title_skipped(self):
        from scrapers.discovery_yc import fetch_listings
        jobs = [
            {**_make_job(job_id=1), "title": ""},
            _make_job(job_id=2),
        ]
        html = _make_html(jobs)
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert len(results) == 1

    def test_missing_company_name_skipped(self):
        from scrapers.discovery_yc import fetch_listings
        jobs = [
            {**_make_job(job_id=1), "companyName": ""},
            _make_job(job_id=2),
        ]
        html = _make_html(jobs)
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert len(results) == 1

    def test_multiple_jobs_returned(self):
        from scrapers.discovery_yc import fetch_listings
        jobs = [_make_job(job_id=i) for i in range(1, 5)]
        html = _make_html(jobs)
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_listings()
        assert len(results) == 4

    def test_empty_jobs_list_returns_empty(self):
        from scrapers.discovery_yc import fetch_listings
        html = _make_html([])
        with patch("scrapers.discovery_yc.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_listings()
        assert results == []
        assert geo == 0
