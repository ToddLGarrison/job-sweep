from unittest.mock import MagicMock, patch

import pytest

from scrapers.smartrecruiters import _extract_location, fetch_jobs


def _posting(
    name="Solutions Engineer",
    ref="https://jobs.smartrecruiters.com/Acme/123",
    location=None,
    sections=None,
):
    loc = location if location is not None else {"country": "US", "city": "Austin", "region": "TX", "remote": False}
    return {
        "name": name,
        "ref": ref,
        "location": loc,
        "jobAd": {"sections": sections or {}},
    }


def _api_response(postings, total=None):
    return {"content": postings, "totalFound": total if total is not None else len(postings)}


# --- _extract_location ---

class TestExtractLocation:
    def test_remote(self):
        assert _extract_location({"remote": True}) == "Remote"

    def test_us_city_region(self):
        assert _extract_location({"country": "US", "city": "Austin", "region": "TX", "remote": False}) == "Austin, TX"

    def test_us_country_string(self):
        assert _extract_location({"country": "United States", "city": "", "region": "", "remote": False}) == "United States"

    def test_non_us_city_country(self):
        assert _extract_location({"country": "India", "city": "Hyderabad", "remote": False}) == "Hyderabad, India"

    def test_non_us_country_only(self):
        assert _extract_location({"country": "Germany", "city": "", "remote": False}) == "Germany"

    def test_empty_dict(self):
        assert _extract_location({}) == ""

    def test_usa_string(self):
        assert _extract_location({"country": "USA", "city": "Denver", "region": "CO", "remote": False}) == "Denver, CO"


# --- fetch_jobs ---

class TestFetchJobs:
    def _mock_get(self, responses):
        """responses: list of dicts to return as .json() in sequence."""
        mock = MagicMock()
        mock.raise_for_status = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = responses[call_count]
            call_count += 1
            return resp

        return side_effect

    def test_returns_job_listing_objects(self):
        postings = [_posting()]
        response = _api_response(postings)
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = response
            listings, geo_filtered = fetch_jobs("acme")
        assert len(listings) == 1
        assert listings[0].title == "Solutions Engineer"
        assert listings[0].url == "https://jobs.smartrecruiters.com/Acme/123"
        assert listings[0].location == "Austin, TX"
        assert geo_filtered == 0

    def test_geo_location_filter_excludes_non_us(self):
        postings = [
            _posting(location={"country": "India", "city": "Hyderabad", "remote": False}),
        ]
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response(postings)
            listings, geo_filtered = fetch_jobs("acme")
        assert listings == []
        assert geo_filtered == 1

    def test_title_geo_filter_excludes_emea(self):
        postings = [_posting(name="Solutions Engineer, EMEA")]
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response(postings)
            listings, geo_filtered = fetch_jobs("acme")
        assert listings == []
        assert geo_filtered == 1

    def test_title_geo_filter_excludes_japan(self):
        postings = [_posting(name="Customer Success Manager, Japan")]
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response(postings)
            listings, geo_filtered = fetch_jobs("acme")
        assert listings == []
        assert geo_filtered == 1

    def test_remote_posting_passes_geo_filter(self):
        postings = [_posting(location={"remote": True})]
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response(postings)
            listings, geo_filtered = fetch_jobs("acme")
        assert len(listings) == 1
        assert listings[0].location == "Remote"

    def test_pagination_fetches_all_pages(self):
        page1 = _posting(name="Solutions Engineer", ref="https://jobs.sr.com/1")
        page2 = _posting(name="Customer Success Manager", ref="https://jobs.sr.com/2")

        responses = [
            {"content": [page1], "totalFound": 2},
            {"content": [page2], "totalFound": 2},
            {"content": [], "totalFound": 2},
        ]

        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.side_effect = self._mock_get(responses)
            listings, geo_filtered = fetch_jobs("acme")

        assert len(listings) == 2
        assert mock_get.call_count == 2  # stops when offset >= totalFound after page 2

    def test_http_error_returns_empty_list(self):
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.side_effect = Exception("connection timeout")
            listings, geo_filtered = fetch_jobs("acme")
        assert listings == []
        assert geo_filtered == 0

    def test_http_status_error_returns_empty_list(self):
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock = MagicMock()
            mock.raise_for_status.side_effect = Exception("404 Not Found")
            mock_get.return_value = mock
            listings, geo_filtered = fetch_jobs("acme")
        assert listings == []
        assert geo_filtered == 0

    def test_description_extracted_from_sections(self):
        posting = _posting(sections={
            "jobDescription": {"text": "<p>Join our team.</p>"},
            "qualifications": {"text": "3+ years experience"},
        })
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response([posting])
            listings, _ = fetch_jobs("acme")
        assert "Join our team" in listings[0].description
        assert "3+ years experience" in listings[0].description

    def test_missing_title_or_url_skipped(self):
        postings = [
            {"name": "", "ref": "https://jobs.sr.com/1", "location": {"country": "US", "remote": False}, "jobAd": {"sections": {}}},
            {"name": "Solutions Engineer", "ref": "", "location": {"country": "US", "remote": False}, "jobAd": {"sections": {}}},
        ]
        with patch("scrapers.smartrecruiters.requests.get") as mock_get:
            mock_get.return_value.raise_for_status = MagicMock()
            mock_get.return_value.json.return_value = _api_response(postings)
            listings, _ = fetch_jobs("acme")
        assert listings == []
