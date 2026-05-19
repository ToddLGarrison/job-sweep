from unittest.mock import MagicMock, patch

import pytest


def _mock_response(text, url=None, content_type="application/xml"):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.text = text
    resp.url = url or "https://jobs.jobvite.com/acme/feed"
    resp.headers = {"content-type": content_type}
    return resp


def _make_xml(jobs):
    job_xml = ""
    for j in jobs:
        job_xml += f"""
        <job>
          <title>{j.get('title', '')}</title>
          <apply-url>{j.get('url', '')}</apply-url>
          <location>{j.get('location', '')}</location>
        </job>"""
    return f"<?xml version='1.0'?><jobs>{job_xml}</jobs>"


class TestFetchJobs:
    def test_returns_job_listings_from_xml(self):
        from scrapers.jobvite import fetch_jobs
        xml = _make_xml([{"title": "Solutions Engineer", "url": "https://jobs.jobvite.com/acme/job/abc", "location": "Remote"}])
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(xml, content_type="application/xml")):
            results, geo = fetch_jobs("acme")
        assert len(results) == 1
        assert results[0].title == "Solutions Engineer"
        assert results[0].location == "Remote"
        assert geo == 0

    def test_support_page_redirect_returns_empty(self):
        from scrapers.jobvite import fetch_jobs
        support_url = "https://www.jobvite.com/support/job-seeker-support/"
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(
            "<html>support page</html>",
            url=support_url,
            content_type="text/html",
        )):
            results, geo = fetch_jobs("badslug")
        assert results == []
        assert geo == 0

    def test_support_page_in_body_returns_empty(self):
        from scrapers.jobvite import fetch_jobs
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(
            "jobvite.com/support something",
            content_type="text/html",
        )):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_geo_filter_excludes_non_us(self):
        from scrapers.jobvite import fetch_jobs
        xml = _make_xml([{"title": "SE", "url": "https://jobs.jobvite.com/acme/job/x", "location": "London, UK"}])
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(xml)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_title_geo_filter_excludes_emea(self):
        from scrapers.jobvite import fetch_jobs
        xml = _make_xml([{"title": "SE EMEA", "url": "https://jobs.jobvite.com/acme/job/x", "location": "Remote"}])
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(xml)):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 1

    def test_http_error_returns_empty(self):
        from scrapers.jobvite import fetch_jobs
        with patch("scrapers.jobvite.requests.get", side_effect=Exception("connection refused")):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_non_xml_content_type_returns_empty(self):
        from scrapers.jobvite import fetch_jobs
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(
            "<html>some page</html>", content_type="text/html"
        )):
            results, geo = fetch_jobs("acme")
        assert results == []
        assert geo == 0

    def test_missing_title_or_url_skipped(self):
        from scrapers.jobvite import fetch_jobs
        xml = """<?xml version='1.0'?><jobs>
        <job><title></title><apply-url>https://jobs.jobvite.com/x</apply-url><location>Remote</location></job>
        <job><title>Good</title><apply-url></apply-url><location>Remote</location></job>
        </jobs>"""
        with patch("scrapers.jobvite.requests.get", return_value=_mock_response(xml)):
            results, _ = fetch_jobs("acme")
        assert results == []
