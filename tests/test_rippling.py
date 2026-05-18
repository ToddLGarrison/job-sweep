import json
from unittest.mock import MagicMock, patch

import pytest


def _make_next_data(items, total_items=None):
    return json.dumps({
        "props": {
            "pageProps": {
                "jobs": {
                    "items": items,
                    "page": 0,
                    "pageSize": 1000,
                    "totalItems": total_items if total_items is not None else len(items),
                    "totalPages": 1,
                }
            }
        }
    })


def _make_html(items, total_items=None):
    nd = _make_next_data(items, total_items)
    return f'<html><head></head><body><script id="__NEXT_DATA__" type="application/json">{nd}</script></body></html>'


def _make_item(
    job_id="abc-123",
    name="Solutions Engineer",
    country="United States",
    country_code="US",
    city="New York",
    state="New York",
    state_code="NY",
    workplace_type="ON_SITE",
):
    return {
        "id": job_id,
        "name": name,
        "url": f"https://ats.rippling.com/acme/jobs/{job_id}",
        "department": {"name": "Sales"},
        "locations": [
            {
                "name": f"{city}, {state_code}",
                "country": country,
                "countryCode": country_code,
                "state": state,
                "stateCode": state_code,
                "city": city,
                "workplaceType": workplace_type,
            }
        ],
    }


def _mock_response(html, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    if status != 200:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    resp.text = html
    return resp


class TestFetchJobs:
    def test_returns_job_listing_objects(self):
        from scrapers.rippling import fetch_jobs
        html = _make_html([_make_item()])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert "abc-123" in results[0].url
        assert geo == 0

    def test_location_extracted_correctly(self):
        from scrapers.rippling import fetch_jobs
        html = _make_html([_make_item(city="San Francisco", state_code="CA")])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "San Francisco, CA"

    def test_remote_workplace_type_sets_remote_location(self):
        from scrapers.rippling import fetch_jobs
        html = _make_html([_make_item(workplace_type="REMOTE")])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "Remote"

    def test_geo_filter_excludes_non_us(self):
        from scrapers.rippling import fetch_jobs
        html = _make_html([_make_item(country="Poland", country_code="PL", city="Warsaw", state="", state_code="")])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_title_geo_filter_excludes_apac(self):
        from scrapers.rippling import fetch_jobs
        html = _make_html([_make_item(name="Solutions Engineer - APAC")])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_http_error_returns_empty_list(self):
        from scrapers.rippling import fetch_jobs
        with patch("scrapers.rippling.requests.get", side_effect=Exception("timeout")):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_http_status_error_returns_empty_list(self):
        from scrapers.rippling import fetch_jobs
        with patch("scrapers.rippling.requests.get", return_value=_mock_response("", status=404)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_next_data_returns_empty(self):
        from scrapers.rippling import fetch_jobs
        html = "<html><body>No data here</body></html>"
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_name_or_url_skipped(self):
        from scrapers.rippling import fetch_jobs
        items = [
            {"id": "1", "name": "", "url": "https://ats.rippling.com/acme/jobs/1", "locations": []},
            {"id": "2", "name": "Good Title", "url": "", "locations": []},
        ]
        html = _make_html(items)
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results == []

    def test_multiple_jobs_returned(self):
        from scrapers.rippling import fetch_jobs
        items = [_make_item(job_id="a"), _make_item(job_id="b"), _make_item(job_id="c")]
        html = _make_html(items)
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert len(results) == 3

    def test_no_locations_returns_empty_location(self):
        from scrapers.rippling import fetch_jobs
        item = _make_item()
        item["locations"] = []
        html = _make_html([item])
        with patch("scrapers.rippling.requests.get", return_value=_mock_response(html)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == ""
