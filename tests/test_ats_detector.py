import pytest

from scrapers.ats_detector import detect_ats, extract_ats_domain


class TestDetectAts:
    # --- Greenhouse ---
    def test_greenhouse_job_boards_domain(self):
        url = "https://job-boards.greenhouse.io/snyk/jobs/7920513905"
        assert detect_ats(url) == ("Greenhouse", "snyk")

    def test_greenhouse_boards_domain(self):
        url = "https://boards.greenhouse.io/cyera/jobs/4567890"
        assert detect_ats(url) == ("Greenhouse", "cyera")

    def test_greenhouse_with_utm_params(self):
        url = "https://job-boards.greenhouse.io/acme/jobs/123?utm_source=linkedin"
        assert detect_ats(url) == ("Greenhouse", "acme")

    # --- Lever ---
    def test_lever_standard(self):
        url = "https://jobs.lever.co/automattic/abc12345-6789-def0-1234-56789abcdef0"
        assert detect_ats(url) == ("Lever", "automattic")

    def test_lever_with_trailing_path(self):
        url = "https://jobs.lever.co/stripe/aaaabbbb-cccc-dddd-eeee-ffffffffffff/apply"
        assert detect_ats(url) == ("Lever", "stripe")

    # --- Ashby ---
    def test_ashby_standard(self):
        url = "https://jobs.ashbyhq.com/bestow/affb8966-2538-44d7-b334-07f152ff73fc"
        assert detect_ats(url) == ("Ashby", "bestow")

    def test_ashby_with_utm(self):
        url = "https://jobs.ashbyhq.com/checkly/88c7e552-009b-4db7-a23b-1c3dd7779930?utm_source=vf"
        assert detect_ats(url) == ("Ashby", "checkly")

    # --- Workday ---
    def test_workday_without_locale(self):
        url = "https://snyk.wd103.myworkdayjobs.com/External/job/United-States---Boston-Office/Senior-Solutions-Engineer_JR100617"
        result = detect_ats(url)
        assert result == ("Workday", "snyk.wd103/External")

    def test_workday_with_en_us_locale(self):
        url = "https://rb.wd5.myworkdayjobs.com/en-US/FRS/job/Solutions-Engineer_R-0000031756"
        result = detect_ats(url)
        assert result == ("Workday", "rb.wd5/FRS")

    def test_workday_autodesk(self):
        url = "https://autodesk.wd1.myworkdayjobs.com/en-US/Ext/job/Austin-TX/SE_R-999"
        result = detect_ats(url)
        assert result == ("Workday", "autodesk.wd1/Ext")

    def test_workday_slug_lowercased(self):
        url = "https://Gainsight.WD5.myworkdayjobs.com/Gainsight_External_Careers/job/Role_123"
        result = detect_ats(url)
        assert result == ("Workday", "gainsight.wd5/Gainsight_External_Careers")

    # --- SmartRecruiters ---
    def test_smartrecruiters_standard(self):
        url = "https://jobs.smartrecruiters.com/Acme/74005000-solutions-engineer"
        assert detect_ats(url) == ("SmartRecruiters", "Acme")

    def test_smartrecruiters_with_job_id(self):
        url = "https://jobs.smartrecruiters.com/BigCorp/743999999123-customer-success"
        assert detect_ats(url) == ("SmartRecruiters", "BigCorp")

    # --- Comeet ---
    def test_comeet_standard(self):
        url = "https://www.comeet.com/jobs/cyera/17.008/solutions-engineer/A1.234"
        assert detect_ats(url) == ("Comeet", "cyera/17.008")

    def test_comeet_akeyless(self):
        url = "https://www.comeet.com/jobs/akeyless/27.006/customer-success-engineer/4B.162"
        assert detect_ats(url) == ("Comeet", "akeyless/27.006")

    # --- Unknown / No match ---
    def test_unknown_ats_returns_none(self):
        url = "https://searchjobs.libertymutualgroup.com/careers/job/618516127729"
        assert detect_ats(url) is None

    def test_internal_ats_returns_none(self):
        url = "https://careers.google.com/jobs/results/123456"
        assert detect_ats(url) is None

    def test_empty_string_returns_none(self):
        assert detect_ats("") is None

    def test_non_ats_url_returns_none(self):
        assert detect_ats("https://www.linkedin.com/jobs/view/123") is None


class TestExtractAtsDomain:
    def test_known_ats_url(self):
        url = "https://job-boards.greenhouse.io/snyk/jobs/7920513905"
        assert extract_ats_domain(url) == "job-boards.greenhouse.io"

    def test_unknown_ats_url(self):
        assert extract_ats_domain("https://searchjobs.libertymutualgroup.com/careers/job/123") == "searchjobs.libertymutualgroup.com"

    def test_jobvite_domain(self):
        assert extract_ats_domain("https://jobs.jobvite.com/acme/job/abc123") == "jobs.jobvite.com"

    def test_icims_domain(self):
        assert extract_ats_domain("https://careers.icims.com/jobs/1234/se/job") == "careers.icims.com"

    def test_empty_string_returns_empty(self):
        assert extract_ats_domain("") == ""

    def test_unparseable_input_returns_empty(self):
        assert extract_ats_domain("not a url") == ""

    def test_strips_path_and_query(self):
        url = "https://recruiting.ultipro.com/ACM1000/JobBoard/abc?utm_source=vf"
        assert extract_ats_domain(url) == "recruiting.ultipro.com"
