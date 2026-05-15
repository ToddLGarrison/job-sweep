from unittest.mock import MagicMock, call, patch

import pytest

from scrapers.workday import fetch_jobs


def _posting(
    title="Solutions Engineer",
    locations_text="San Francisco, CA, United States",
    external_path="/job/San-Francisco-CA/Solutions-Engineer_R-12345",
):
    return {"title": title, "locationsText": locations_text, "externalPath": external_path}


def _api_response(postings, total=None):
    return {"jobPostings": postings, "total": total if total is not None else len(postings)}


def _mock_post(responses):
    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = responses[call_count]
        call_count += 1
        return resp

    return side_effect


# --- fetch_jobs ---

class TestFetchJobs:
    def test_returns_job_listing_objects(self):
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([_posting()])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert listings[0].title == "Solutions Engineer"
        assert listings[0].location == "San Francisco, CA"
        assert geo_filtered == 0

    def test_apply_url_constructed_correctly(self):
        posting = _posting(external_path="/job/Austin-TX/SE_R-999")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, _ = fetch_jobs("autodesk.wd1/Ext")
        assert listings[0].url == "https://autodesk.wd1.myworkdayjobs.com/en-US/Ext/job/Austin-TX/SE_R-999"

    def test_slug_parsing_subdomain_and_board(self):
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([])
            fetch_jobs("accenture.wd103/AccentureCareers")
        called_url = mock_post.call_args[0][0]
        assert called_url == "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs"

    def test_geo_filter_excludes_non_us(self):
        posting = _posting(locations_text="Hyderabad, India")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 1

    def test_title_geo_filter_excludes_emea(self):
        posting = _posting(title="Solutions Engineer, EMEA")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 1

    def test_title_geo_filter_excludes_apac(self):
        posting = _posting(title="Customer Success Manager, Japan")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 1

    def test_remote_passes_geo_filter(self):
        posting = _posting(locations_text="Remote, United States")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert listings[0].location == "Remote"
        assert geo_filtered == 0

    def test_pagination_fetches_all_pages(self):
        page1 = [_posting(title="SE 1", external_path="/job/X/SE1_R1")] * 20
        page2 = [_posting(title="SE 2", external_path="/job/X/SE2_R2")] * 5
        responses = [
            _api_response(page1, total=25),
            _api_response(page2, total=25),
        ]
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.side_effect = _mock_post(responses)
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 25
        assert mock_post.call_count == 2

    def test_pagination_passes_correct_offsets(self):
        page1 = [_posting()] * 20
        page2 = [_posting(title="CSM", external_path="/job/X/CSM_R2")]
        responses = [
            _api_response(page1, total=21),
            _api_response(page2, total=21),
        ]
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.side_effect = _mock_post(responses)
            fetch_jobs("autodesk.wd1/Ext")
        offsets = [c.kwargs["json"]["offset"] for c in mock_post.call_args_list]
        assert offsets == [0, 20]

    def test_http_error_returns_empty(self):
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.side_effect = Exception("connection timeout")
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 0

    def test_http_status_error_returns_empty(self):
        with patch("scrapers.workday.requests.post") as mock_post:
            mock = MagicMock()
            mock.raise_for_status.side_effect = Exception("403 Forbidden")
            mock_post.return_value = mock
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 0

    def test_missing_title_skipped(self):
        posting = _posting(title="")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, _ = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []

    def test_missing_external_path_skipped(self):
        posting = _posting(external_path="")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, _ = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []

    def test_trailing_united_states_stripped(self):
        posting = _posting(locations_text="Austin, TX, United States")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, _ = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings[0].location == "Austin, TX"

    def test_non_us_location_not_stripped(self):
        posting = _posting(locations_text="London, United Kingdom")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 1

    def test_workday_country_code_format_usa_remote(self):
        posting = _posting(locations_text="USA - CA - Remote")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert listings[0].location == "Remote"
        assert geo_filtered == 0

    def test_workday_country_code_format_usa_city(self):
        posting = _posting(locations_text="USA - TX - Austin")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert listings[0].location == "Austin, TX"
        assert geo_filtered == 0

    def test_workday_country_code_format_non_us_filtered(self):
        for loc_text in ["POL - Wroclaw", "IND - Remote", "MEX - Remote", "IND - Bengaluru"]:
            posting = _posting(locations_text=loc_text)
            with patch("scrapers.workday.requests.post") as mock_post:
                mock_post.return_value.raise_for_status = MagicMock()
                mock_post.return_value.json.return_value = _api_response([posting])
                listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
            assert listings == [], f"Expected {loc_text} to be filtered, but was kept"
            assert geo_filtered == 1, f"Expected geo_filtered=1 for {loc_text}"

    def test_workday_multi_location_passes_through(self):
        posting = _posting(locations_text="44 Locations")
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([posting])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert listings[0].location == ""

    def test_empty_response_returns_empty(self):
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response([])
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert listings == []
        assert geo_filtered == 0

    def test_mixed_geo_counted_correctly(self):
        postings = [
            _posting(title="SE US", locations_text="San Francisco, CA, United States"),
            _posting(title="SE India", locations_text="Hyderabad, India", external_path="/job/X/R2"),
            _posting(title="SE EMEA", locations_text="Remote, United States", external_path="/job/X/R3"),
        ]
        with patch("scrapers.workday.requests.post") as mock_post:
            mock_post.return_value.raise_for_status = MagicMock()
            mock_post.return_value.json.return_value = _api_response(postings)
            listings, geo_filtered = fetch_jobs("gainsight.wd5/Gainsight_External_Careers")
        assert len(listings) == 1
        assert geo_filtered == 2
