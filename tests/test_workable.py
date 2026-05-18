from unittest.mock import MagicMock, patch, call

import pytest


def _make_posting(
    shortcode="ABC123",
    title="Solutions Engineer",
    state="published",
    remote=False,
    location=None,
):
    return {
        "shortcode": shortcode,
        "title": title,
        "state": state,
        "remote": remote,
        "location": location or {"countryCode": "US", "city": "Boston", "region": "MA"},
    }


def _mock_response(results, next_page=None, total=None):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "results": results,
        "total": total if total is not None else len(results),
        "nextPage": next_page,
    }
    return resp


class TestFetchJobs:
    def test_returns_job_listing_objects(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting()]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert results[0].url == "https://apply.workable.com/acme/j/ABC123"
        assert geo == 0

    def test_apply_url_constructed_correctly(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(shortcode="XYZ999")]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, _ = fetch_jobs("mycompany")
        assert results[0].url == "https://apply.workable.com/mycompany/j/XYZ999"

    def test_skips_unpublished_postings(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(state="draft")]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, _ = fetch_jobs("acme")
        assert results == []

    def test_remote_posting_returns_remote_location(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(remote=True, location={})]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "Remote"

    def test_geo_filter_excludes_non_us(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(location={"countryCode": "GB", "city": "London", "country": "United Kingdom"})]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_title_geo_filter_excludes_emea(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(title="Solutions Engineer - EMEA")]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_pagination_uses_next_page_token(self):
        from scrapers.workable import fetch_jobs
        page1 = _mock_response([_make_posting("A1")], next_page="TOKEN123")
        page2 = _mock_response([_make_posting("A2")], next_page=None)
        with patch("scrapers.workable.requests.post", side_effect=[page1, page2]) as mock_post:
            results, _ = fetch_jobs("acme")
        assert len(results) == 2
        calls = mock_post.call_args_list
        assert calls[0].kwargs["json"].get("token") is None
        assert calls[1].kwargs["json"]["token"] == "TOKEN123"

    def test_http_error_returns_empty_list(self):
        from scrapers.workable import fetch_jobs
        with patch("scrapers.workable.requests.post", side_effect=Exception("timeout")):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_http_status_error_returns_empty_list(self):
        from scrapers.workable import fetch_jobs
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        with patch("scrapers.workable.requests.post", return_value=mock_resp):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_title_or_shortcode_skipped(self):
        from scrapers.workable import fetch_jobs
        postings = [
            {"shortcode": "ABC", "title": "", "state": "published", "remote": False, "location": {}},
            {"shortcode": "", "title": "Good Title", "state": "published", "remote": False, "location": {}},
        ]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, _ = fetch_jobs("acme")
        assert results == []

    def test_us_location_extracted_correctly(self):
        from scrapers.workable import fetch_jobs
        postings = [_make_posting(location={"countryCode": "US", "city": "New York", "region": "NY"})]
        with patch("scrapers.workable.requests.post", return_value=_mock_response(postings)):
            results, _ = fetch_jobs("acme")
        assert results[0].location == "New York, NY"

    def test_empty_results_stops_pagination(self):
        from scrapers.workable import fetch_jobs
        with patch("scrapers.workable.requests.post", return_value=_mock_response([], next_page="TOKEN")):
            results, _ = fetch_jobs("acme")
        assert results == []
