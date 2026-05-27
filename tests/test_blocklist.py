import datetime
from unittest.mock import MagicMock, patch

import main
from config import COMPANY_BLOCKLIST
from discovery import DiscoveryStats, _process_listings
from models import Company, DiscoveryListing

_TODAY = datetime.date(2026, 5, 22)


def _disc_listing(company_name: str, title: str = "Sales Engineer") -> DiscoveryListing:
    return DiscoveryListing(
        title=title,
        url=f"https://jobs.lever.co/{company_name.lower().replace(' ', '-')}/abc",
        company_name=company_name,
        ats="Lever",
        slug=company_name.lower().replace(" ", "-"),
    )


# --- config ---

class TestCompanyBlocklistConfig:
    def test_jobgether_in_blocklist(self):
        assert "Jobgether" in COMPANY_BLOCKLIST

    def test_blocklist_is_a_set(self):
        assert isinstance(COMPANY_BLOCKLIST, set)


# --- discovery._process_listings ---

class TestBlocklistDiscovery:
    def test_blocklisted_company_is_skipped(self, capsys):
        listing = _disc_listing("Jobgether")
        stats = DiscoveryStats()
        with patch("discovery.notion") as mock_notion, \
             patch("discovery.is_duplicate", return_value=False), \
             patch("discovery.check_red_flags", return_value=[]):
            _process_listings([listing], stats, set(), _TODAY, dry_run=True)
        mock_notion.write_opportunity.assert_not_called()
        assert "SKIP Jobgether / Sales Engineer — blocklisted aggregator" in capsys.readouterr().out

    def test_non_blocklisted_company_passes_through(self):
        listing = _disc_listing("Acme Corp")
        stats = DiscoveryStats()
        mock_company = MagicMock(page_id="p1", name="Acme Corp", ats="Lever", ats_slug="acme")
        with patch("discovery.notion") as mock_notion, \
             patch("discovery.is_duplicate", return_value=False), \
             patch("discovery.check_red_flags", return_value=[]):
            mock_notion.find_company_by_name.return_value = mock_company
            _process_listings([listing], stats, set(), _TODAY, dry_run=True)
        mock_notion.write_opportunity.assert_called_once()

    def test_blocklist_is_case_sensitive(self):
        listing = _disc_listing("jobgether")  # lowercase — not in COMPANY_BLOCKLIST
        stats = DiscoveryStats()
        mock_company = MagicMock(page_id="p1", name="jobgether", ats="Lever", ats_slug="jobgether")
        with patch("discovery.notion") as mock_notion, \
             patch("discovery.is_duplicate", return_value=False), \
             patch("discovery.check_red_flags", return_value=[]):
            mock_notion.find_company_by_name.return_value = mock_company
            _process_listings([listing], stats, set(), _TODAY, dry_run=True)
        mock_notion.write_opportunity.assert_called_once()


# --- main.main() company sweep loop ---

def _run_sweep(company_name: str) -> MagicMock:
    """Run main() with one company that has one title-matching listing; return write_opportunity mock."""
    company = Company(page_id="p1", name=company_name, ats="Lever", ats_slug="slug")
    scraper_listing = MagicMock(
        title="Sales Engineer", url="https://jobs.lever.co/test/abc",
        description="", location="",
    )
    with patch("notion_api._client"), \
         patch("sys.argv", ["main.py", "--dry-run"]), \
         patch("main.notion.fetch_companies", return_value=[company]), \
         patch("main.importlib.import_module") as mock_import, \
         patch("main.notion.write_opportunity") as mock_write, \
         patch("main.notion.update_company"), \
         patch("main.match_title", return_value="Sales Engineer"), \
         patch("main.is_title_geo_excluded", return_value=False), \
         patch("main.check_description_geo", return_value=False), \
         patch("main.is_duplicate", return_value=False), \
         patch("main.check_red_flags", return_value=[]), \
         patch("main.run_discovery", return_value=None), \
         patch("main.run_expiry_check", return_value=MagicMock(
             still_live=0, newly_missed=0, auto_closed=0,
             errors=0, closed_roles=[])), \
         patch("main.write_last_run"), \
         patch("main.read_and_clear_last_run", return_value=None), \
         patch("main.time.sleep"), \
         patch("main._acquire_lock", return_value=MagicMock()):
        mock_scraper = MagicMock()
        mock_scraper.fetch_jobs.return_value = ([scraper_listing], 0)
        mock_import.return_value = mock_scraper
        main.main()
    return mock_write


class TestBlocklistSweep:
    def test_blocklisted_company_not_written(self, capsys):
        mock_write = _run_sweep("Jobgether")
        mock_write.assert_not_called()
        assert "SKIP Jobgether / Sales Engineer — blocklisted aggregator" in capsys.readouterr().out

    def test_non_blocklisted_company_passes_through(self):
        mock_write = _run_sweep("Acme Corp")
        mock_write.assert_called_once()

    def test_blocklist_is_case_sensitive_in_sweep(self):
        mock_write = _run_sweep("jobgether")  # lowercase — not in COMPANY_BLOCKLIST
        mock_write.assert_called_once()
