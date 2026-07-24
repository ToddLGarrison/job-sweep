from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import BUILTINBOSTON_ROTATION_QUEUE, BUILTINBOSTON_TITLES
from scrapers.discovery_builtinboston import (
    BIBCard,
    _Budget,
    _BudgetExceeded,
    _fetch_apply_url,
    _filter_cards,
    _parse_listing_page,
    _parse_salary_ceiling,
    run_rotation,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(fname: str) -> list[BIBCard]:
    return _parse_listing_page((FIXTURES / fname).read_text(encoding="utf-8"))


def _make_card(
    *,
    title="Solutions Engineer",
    company_name="Acme",
    detail_url="https://www.builtinboston.com/job/solutions-engineer/99999",
    job_id=99999,
    is_easy_apply=False,
    seniority_text="Senior level",
    salary_text="100K-150K Annually",
) -> BIBCard:
    return BIBCard(
        title=title,
        company_name=company_name,
        detail_url=detail_url,
        job_id=job_id,
        is_easy_apply=is_easy_apply,
        seniority_text=seniority_text,
        salary_text=salary_text,
    )


# ---------------------------------------------------------------------------
# Parsing layer (29 tests from previous pass — kept intact)
# ---------------------------------------------------------------------------

class TestSolutionsEngineerPage:
    def setup_method(self):
        self.cards = _load("bib_solutions_engineer.html")

    def test_card_count(self):
        assert len(self.cards) == 25

    def test_first_card_full_values(self):
        c = self.cards[0]
        assert c.company_name == "Liberty Mutual Insurance"
        assert c.title == "Solutions Engineer, Software"
        assert c.job_id == 10318066
        assert c.detail_url == "https://www.builtinboston.com/job/solutions-engineer-software/10318066"
        assert c.is_easy_apply is False
        assert c.seniority_text == "Expert/Leader"
        assert c.salary_text == "137K-257K Annually"

    def test_entry_level_card(self):
        c = self.cards[3]
        assert c.company_name == "Dynatrace"
        assert c.title == "Commercial Solutions Engineer (Hybrid, Massachusetts)"
        assert c.seniority_text == "Entry level"
        assert c.salary_text == "72K-90K Annually"

    def test_easy_apply_with_salary(self):
        c = self.cards[4]
        assert c.company_name == "Tulip"
        assert c.title == "Senior Manufacturing Solutions Engineer"
        assert c.is_easy_apply is True
        assert c.salary_text == "90K-130K Annually"

    def test_no_salary_non_easy_apply(self):
        c = self.cards[8]
        assert c.company_name == "Cloudflare"
        assert c.title == "Senior Solutions Engineer, Majors, Philadelphia or Pittsburgh"
        assert c.is_easy_apply is False
        assert c.salary_text is None

    def test_two_more_cloudflare_no_salary(self):
        c14 = self.cards[14]
        c24 = self.cards[24]
        assert c14.company_name == "Cloudflare"
        assert c14.salary_text is None
        assert c24.company_name == "Cloudflare"
        assert c24.salary_text is None

    def test_all_cards_have_seniority(self):
        missing = [c for c in self.cards if c.seniority_text is None]
        assert missing == [], f"Cards missing seniority: {missing}"

    def test_all_job_ids_positive(self):
        assert all(c.job_id > 0 for c in self.cards)

    def test_all_detail_urls_well_formed(self):
        for c in self.cards:
            assert c.detail_url.startswith("https://www.builtinboston.com/job/")
            assert str(c.job_id) in c.detail_url

    def test_easy_apply_count(self):
        assert sum(1 for c in self.cards if c.is_easy_apply) == 8


class TestCustomerSuccessPage:
    def setup_method(self):
        self.cards = _load("bib_customer_success.html")

    def test_card_count(self):
        assert len(self.cards) == 25

    def test_easy_apply_with_salary(self):
        c = self.cards[2]
        assert c.company_name == "Datadog"
        assert c.title == "Enterprise Customer Success Manager - Boston"
        assert c.is_easy_apply is True
        assert c.salary_text == "101K-135K Annually"

    def test_easy_apply_without_salary(self):
        c = self.cards[4]
        assert c.company_name == "Tulip"
        assert c.title == "Customer Success Manager, General Manufacturing"
        assert c.is_easy_apply is True
        assert c.salary_text is None

    def test_expert_leader_seniority(self):
        c = self.cards[1]
        assert c.company_name == "Imprivata"
        assert c.seniority_text == "Expert/Leader"

    def test_junior_seniority(self):
        c = self.cards[16]
        assert c.company_name == "Toast"
        assert c.seniority_text == "Junior"

    def test_all_cards_have_seniority(self):
        missing = [c for c in self.cards if c.seniority_text is None]
        assert missing == [], f"Cards missing seniority: {missing}"

    def test_easy_apply_count(self):
        assert sum(1 for c in self.cards if c.is_easy_apply) == 11


class TestCustomerSuccessSeniorPage:
    def setup_method(self):
        self.cards = _load("bib_customer_success_senior.html")

    def test_card_count(self):
        assert len(self.cards) == 25

    def test_nasuni_csm_no_salary(self):
        c = self.cards[14]
        assert c.company_name == "Nasuni"
        assert c.title == "Customer Success Manager"
        assert c.is_easy_apply is True
        assert c.salary_text is None

    def test_nasuni_senior_csm_no_salary(self):
        c = self.cards[15]
        assert c.company_name == "Nasuni"
        assert c.title == "Senior Customer Success Manager"
        assert c.is_easy_apply is True
        assert c.salary_text is None

    def test_all_cards_have_seniority(self):
        missing = [c for c in self.cards if c.seniority_text is None]
        assert missing == [], f"Cards missing seniority: {missing}"

    def test_easy_apply_count(self):
        assert sum(1 for c in self.cards if c.is_easy_apply) == 15


class TestCrossFixture:
    def setup_method(self):
        self.all_cards = (
            _load("bib_solutions_engineer.html")
            + _load("bib_customer_success.html")
            + _load("bib_customer_success_senior.html")
        )

    def test_total_cards(self):
        assert len(self.all_cards) == 75

    def test_seniority_never_none(self):
        missing = [c for c in self.all_cards if c.seniority_text is None]
        assert missing == [], f"{len(missing)} cards missing seniority_text"

    def test_salary_none_count(self):
        missing = [c for c in self.all_cards if c.salary_text is None]
        assert len(missing) == 6

    def test_all_job_ids_are_positive_ints(self):
        for c in self.all_cards:
            assert isinstance(c.job_id, int)
            assert c.job_id > 0

    def test_detail_url_contains_job_id(self):
        for c in self.all_cards:
            assert str(c.job_id) in c.detail_url

    def test_no_salary_is_none_not_empty_string(self):
        for c in self.all_cards:
            assert c.salary_text != "", "salary_text should be None, not empty string"

    def test_no_seniority_is_none_not_empty_string(self):
        for c in self.all_cards:
            assert c.seniority_text != "", "seniority_text should be None, not empty string"


# ---------------------------------------------------------------------------
# Salary ceiling parser
# ---------------------------------------------------------------------------

class TestParseSalaryCeiling:
    def test_standard_k_range_returns_ceiling(self):
        # "72K-90K" → ceiling is 90K, not the floor 72K
        assert _parse_salary_ceiling("72K-90K Annually") == 90_000

    def test_ceiling_is_second_number(self):
        assert _parse_salary_ceiling("90K-130K Annually") == 130_000

    def test_high_range(self):
        assert _parse_salary_ceiling("137K-257K Annually") == 257_000

    def test_wide_range_with_low_floor(self):
        # 59K floor but 172K ceiling — ceiling clears threshold
        assert _parse_salary_ceiling("59K-172K Annually") == 172_000

    def test_equal_high_low(self):
        # Dragos "140K-140K Annually"
        assert _parse_salary_ceiling("140K-140K Annually") == 140_000

    def test_ceiling_above_threshold_despite_low_floor(self):
        # 60K floor, 101K ceiling — ceiling passes
        assert _parse_salary_ceiling("60K-101K Annually") == 101_000

    def test_narrow_range_above_threshold(self):
        assert _parse_salary_ceiling("85K-95K Annually") == 95_000

    def test_genuine_low_ceiling(self):
        # Both numbers below threshold — ceiling 75K < 80K → would be filtered
        assert _parse_salary_ceiling("60K-75K Annually") == 75_000

    def test_single_number_treated_as_ceiling(self):
        assert _parse_salary_ceiling("95K") == 95_000

    def test_single_number_below_threshold(self):
        assert _parse_salary_ceiling("70K") == 70_000

    def test_returns_none_on_garbage(self):
        assert _parse_salary_ceiling("Competitive") is None

    def test_returns_none_on_empty(self):
        assert _parse_salary_ceiling("") is None


# ---------------------------------------------------------------------------
# Filter function — unit tests with synthetic BIBCards
# ---------------------------------------------------------------------------

class TestFilterCards:
    def test_easy_apply_always_removed(self):
        cards = [
            _make_card(is_easy_apply=True, salary_text="150K-200K Annually"),
            _make_card(is_easy_apply=True, salary_text=None),
            _make_card(is_easy_apply=True, salary_text="50K-70K Annually"),
        ]
        assert _filter_cards(cards) == []

    def test_salary_ceiling_below_threshold_removed(self):
        # ceiling = 75K < 80K → removed (even best case falls short)
        card = _make_card(is_easy_apply=False, salary_text="60K-75K Annually")
        assert _filter_cards([card]) == []

    def test_salary_ceiling_at_threshold_passes(self):
        # ceiling = 80K = threshold → passes (not strictly below)
        card = _make_card(is_easy_apply=False, salary_text="60K-80K Annually")
        assert _filter_cards([card]) == [card]

    def test_salary_ceiling_above_threshold_passes(self):
        # ceiling = 130K >= 80K → passes regardless of floor
        card = _make_card(is_easy_apply=False, salary_text="90K-130K Annually")
        assert _filter_cards([card]) == [card]

    def test_wide_range_low_floor_passes(self):
        # floor 59K but ceiling 172K — ceiling rule keeps it
        card = _make_card(is_easy_apply=False, salary_text="59K-172K Annually")
        assert _filter_cards([card]) == [card]

    def test_wide_range_low_floor_passes_72k_90k(self):
        # Previously filtered under floor rule; ceiling 90K now passes
        card = _make_card(is_easy_apply=False, salary_text="72K-90K Annually")
        assert _filter_cards([card]) == [card]

    def test_none_salary_passes(self):
        # Unknown salary — do not filter
        card = _make_card(is_easy_apply=False, salary_text=None)
        assert _filter_cards([card]) == [card]

    def test_seniority_never_blocks_card(self):
        # Senior-level card with good salary should survive regardless of seniority
        card = _make_card(
            is_easy_apply=False,
            seniority_text="Senior level",
            salary_text="90K-130K Annually",
        )
        assert _filter_cards([card]) == [card]

    def test_seniority_preserved_on_survivor(self):
        card = _make_card(seniority_text="Expert/Leader", salary_text="130K-180K Annually")
        result = _filter_cards([card])
        assert len(result) == 1
        assert result[0].seniority_text == "Expert/Leader"

    def test_mixed_batch(self):
        cards = [
            _make_card(company_name="A", is_easy_apply=True,  salary_text="100K-150K Annually"),  # easy apply → out
            _make_card(company_name="B", is_easy_apply=False, salary_text="60K-75K Annually"),    # ceiling 75K < 80K → out
            _make_card(company_name="C", is_easy_apply=False, salary_text="72K-90K Annually"),    # ceiling 90K ≥ 80K → in
            _make_card(company_name="D", is_easy_apply=False, salary_text="90K-130K Annually"),   # passes
            _make_card(company_name="E", is_easy_apply=False, salary_text=None),                  # no salary → passes
            _make_card(company_name="F", is_easy_apply=True,  salary_text=None),                  # easy apply → out
        ]
        survivors = _filter_cards(cards)
        names = [c.company_name for c in survivors]
        assert names == ["C", "D", "E"]

    def test_empty_input(self):
        assert _filter_cards([]) == []


# ---------------------------------------------------------------------------
# Blocklist filtering (happens before detail fetch)
# ---------------------------------------------------------------------------

class TestFilterCardsBlocklist:
    """Blocklisted companies must be removed by _filter_cards, not after detail fetch."""

    def test_zs_filtered(self):
        card = _make_card(company_name="ZS")
        assert _filter_cards([card]) == []

    def test_pwc_filtered(self):
        card = _make_card(company_name="PwC")
        assert _filter_cards([card]) == []

    def test_jobgether_filtered(self):
        card = _make_card(company_name="Jobgether")
        assert _filter_cards([card]) == []

    def test_liberty_mutual_filtered(self):
        card = _make_card(company_name="Liberty Mutual Insurance")
        assert _filter_cards([card]) == []

    def test_massmutual_filtered(self):
        card = _make_card(company_name="MassMutual")
        assert _filter_cards([card]) == []

    def test_blocklist_applies_regardless_of_salary(self):
        # Good salary doesn't override blocklist
        card = _make_card(company_name="ZS", salary_text="200K-300K Annually")
        assert _filter_cards([card]) == []

    def test_non_blocklisted_company_passes(self):
        card = _make_card(company_name="Acme")
        assert _filter_cards([card]) == [card]

    def test_blocklisted_and_good_cards_mixed(self):
        zs = _make_card(company_name="ZS", detail_url="https://bib.com/job/zs/1", job_id=1)
        good = _make_card(company_name="Acme", detail_url="https://bib.com/job/acme/2", job_id=2)
        assert _filter_cards([zs, good]) == [good]

    def test_blocklisted_card_never_reaches_fetch(self, monkeypatch, tmp_path):
        """run_rotation must not call _fetch_apply_url for a blocklisted company."""
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)

        zs_card = _make_card(
            company_name="ZS",
            detail_url="https://www.builtinboston.com/job/zs-role/1",
            job_id=1,
        )
        good_card = _make_card(
            company_name="Acme",
            detail_url="https://www.builtinboston.com/job/acme-role/2",
            job_id=2,
        )

        listing_resp = MagicMock(status_code=200, text="<html></html>")
        listing_resp.raise_for_status = MagicMock()

        with patch("scrapers.discovery_builtinboston.requests.get", return_value=listing_resp), \
             patch("scrapers.discovery_builtinboston._parse_listing_page", return_value=[zs_card, good_card]), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation([f"kw{i}" for i in range(24)])

        # Only good_card should trigger a detail fetch; ZS must be filtered
        assert mock_fetch.call_count == 1
        assert mock_fetch.call_args[0][0] == good_card.detail_url


# ---------------------------------------------------------------------------
# Filter counts verified against real fixture data
# ---------------------------------------------------------------------------

class TestFixtureFilterCounts:
    """
    Verify exact before/after counts for each fixture page.
    Ceiling-based salary filter: only cards where even the MAX salary < $80K are removed.
    None of the current fixtures contain a genuine ceiling-below-$80K card.
    Update counts only if fixtures are re-fetched from the live site.
    """

    def test_solutions_engineer_survivors(self):
        # 25 total: 8 easy apply, 2 Liberty Mutual Insurance (blocklist), 0 salary → 15 survive
        cards = _load("bib_solutions_engineer.html")
        survivors = _filter_cards(cards)
        assert len(survivors) == 15

    def test_solutions_engineer_easy_apply_none_survive(self):
        cards = _load("bib_solutions_engineer.html")
        survivors = _filter_cards(cards)
        assert not any(c.is_easy_apply for c in survivors)

    def test_solutions_engineer_wide_range_low_floor_survives(self):
        # Dynatrace (72K-90K, ceiling 90K) and Snyk (59K-172K, ceiling 172K) now survive
        cards = _load("bib_solutions_engineer.html")
        survivors = _filter_cards(cards)
        dynatrace_72k = [
            c for c in survivors
            if c.company_name == "Dynatrace" and "72K" in (c.salary_text or "")
        ]
        assert len(dynatrace_72k) == 1
        snyk = [c for c in survivors if c.company_name == "Snyk"]
        assert len(snyk) == 1

    def test_solutions_engineer_none_salary_survives(self):
        # 3 Cloudflare cards with no salary should all pass through
        cards = _load("bib_solutions_engineer.html")
        survivors = _filter_cards(cards)
        cloudflare_no_salary = [
            c for c in survivors
            if c.company_name == "Cloudflare" and c.salary_text is None
        ]
        assert len(cloudflare_no_salary) == 3

    def test_customer_success_survivors(self):
        # 25 total: 11 easy apply, 0 salary (all ceilings ≥ 80K) → 14 survive
        cards = _load("bib_customer_success.html")
        survivors = _filter_cards(cards)
        assert len(survivors) == 14

    def test_customer_success_easy_apply_none_survive(self):
        cards = _load("bib_customer_success.html")
        survivors = _filter_cards(cards)
        assert not any(c.is_easy_apply for c in survivors)

    def test_customer_success_previously_floor_filtered_now_survive(self):
        # SailPoint (60K-101K), Toast (76K-122K), Vetcove (70K-110K), Arcadia (70K-112K)
        # all have ceilings ≥ 80K and now survive
        cards = _load("bib_customer_success.html")
        survivors = _filter_cards(cards)
        sailpoint = [c for c in survivors if c.company_name == "SailPoint"]
        toast = [c for c in survivors if c.company_name == "Toast"]
        vetcove = [c for c in survivors if c.company_name == "Vetcove"]
        arcadia = [c for c in survivors if c.company_name == "Arcadia"]
        assert len(sailpoint) == 2   # two SailPoint CSM cards
        assert len(toast) == 1
        assert len(vetcove) == 1
        assert len(arcadia) == 1

    def test_customer_success_senior_survivors(self):
        # 25 total: 15 easy apply, 0 salary (Arcadia ceiling 112K ≥ 80K) → 10 survive
        cards = _load("bib_customer_success_senior.html")
        survivors = _filter_cards(cards)
        assert len(survivors) == 10

    def test_customer_success_senior_easy_apply_none_survive(self):
        cards = _load("bib_customer_success_senior.html")
        survivors = _filter_cards(cards)
        assert not any(c.is_easy_apply for c in survivors)

    def test_customer_success_senior_arcadia_survives(self):
        # Arcadia (70K-112K), ceiling 112K ≥ 80K → survives
        cards = _load("bib_customer_success_senior.html")
        survivors = _filter_cards(cards)
        arcadia = [c for c in survivors if c.company_name == "Arcadia"]
        assert len(arcadia) == 1


# ---------------------------------------------------------------------------
# run_rotation — mock tests replacing the old fetch_listings tests
# ---------------------------------------------------------------------------

def _listing_resp(fixture_name: str) -> MagicMock:
    html = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    resp = MagicMock()
    resp.status_code = 200
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


class TestRunRotationFilter:
    """
    Verify that run_rotation calls _fetch_apply_url exactly N times,
    where N is the number of cards that survive _filter_cards.
    Easy Apply and low-salary cards must never trigger a detail-page fetch.
    """

    def test_detail_fetch_count_matches_survivors(self, monkeypatch, tmp_path):
        # customer_success: 11 easy apply removed, 0 salary removed → 14 survive
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=_listing_resp("bib_customer_success.html")), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Customer Success Manager"])
        assert mock_fetch.call_count == 14

    def test_easy_apply_card_never_reaches_fetch(self, monkeypatch, tmp_path):
        # Tulip (job_id=7175847) is Easy Apply on customer_success fixture
        tulip_detail_url = "https://www.builtinboston.com/job/customer-success-manager/7175847"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=_listing_resp("bib_customer_success.html")), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Customer Success Manager"])
        called_urls = [c.args[0] for c in mock_fetch.call_args_list]
        assert tulip_detail_url not in called_urls

    def test_wide_range_low_floor_card_reaches_fetch(self, monkeypatch, tmp_path):
        # Snyk (59K-172K) and Dynatrace (72K-90K): ceiling ≥ 80K → reach _fetch_apply_url
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=_listing_resp("bib_solutions_engineer.html")), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"])
        called_urls = [c.args[0] for c in mock_fetch.call_args_list]
        assert any("10220193" in u for u in called_urls)  # Snyk job_id
        assert any("8999600" in u for u in called_urls)   # Dynatrace (72K-90K) job_id

    def test_senior_card_with_good_salary_gets_fetch(self, monkeypatch, tmp_path):
        # solutions_engineer: 15 survivors (8 easy apply + 2 Liberty Mutual removed)
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=_listing_resp("bib_solutions_engineer.html")), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"])
        assert mock_fetch.call_count == 15
        called_urls = [c.args[0] for c in mock_fetch.call_args_list]
        # Drata "Senior Solutions Engineer, Enterprise - West" (224K-277K)
        assert any("8896533" in u for u in called_urls)  # Drata job_id

    def test_seen_detail_urls_dedup_respected(self, monkeypatch, tmp_path):
        # Pre-populate seen_detail_urls with all Drata URLs from solutions_engineer
        cards = _load("bib_solutions_engineer.html")
        drata_urls = {c.detail_url for c in cards if c.company_name == "Drata"}
        assert len(drata_urls) == 3  # sanity check: 3 Drata cards
        seen = set(drata_urls)
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=_listing_resp("bib_solutions_engineer.html")), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", return_value="") as mock_fetch, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"], seen_detail_urls=seen)
        # 15 survivors minus 3 pre-seen Drata cards = 12 detail fetches
        assert mock_fetch.call_count == 12

    def test_listing_403_returns_blocked_count(self, monkeypatch, tmp_path):
        resp_403 = MagicMock()
        resp_403.status_code = 403
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=resp_403), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url") as mock_fetch:
            results, unknown, blocked = run_rotation(["Solutions Engineer"])
        assert results == []
        assert blocked == 1
        mock_fetch.assert_not_called()


# ---------------------------------------------------------------------------
# _Budget — unit tests
# ---------------------------------------------------------------------------

class TestBudget:
    def test_allows_up_to_cap(self):
        budget = _Budget(cap=3)
        budget.request()
        budget.request()
        budget.request()
        with pytest.raises(_BudgetExceeded):
            budget.request()

    def test_count_increments_on_each_request(self):
        budget = _Budget(cap=5)
        budget.request()
        budget.request()
        assert budget.count == 2

    def test_raises_immediately_when_at_cap(self):
        budget = _Budget(cap=0)
        with pytest.raises(_BudgetExceeded):
            budget.request()


# ---------------------------------------------------------------------------
# _fetch_apply_url — budget counting unit tests
# ---------------------------------------------------------------------------

class TestFetchApplyUrlBudget:
    def _ok_resp(self, text: str = "") -> MagicMock:
        resp = MagicMock(status_code=200, text=text)
        resp.raise_for_status = MagicMock()
        return resp

    def _429_resp(self) -> MagicMock:
        return MagicMock(status_code=429)

    def test_successful_fetch_consumes_one_slot(self):
        budget = _Budget(cap=5)
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=self._ok_resp()):
            _fetch_apply_url("https://bib.com/job/1", budget)
        assert budget.count == 1

    def test_retry_after_429_consumes_two_slots(self):
        budget = _Budget(cap=5)
        with patch(
            "scrapers.discovery_builtinboston.requests.get",
            side_effect=[self._429_resp(), self._ok_resp()],
        ), patch("scrapers.discovery_builtinboston.time.sleep"):
            _fetch_apply_url("https://bib.com/job/1", budget)
        assert budget.count == 2

    def test_budget_exceeded_before_initial_request(self):
        budget = _Budget(cap=0)
        with patch("scrapers.discovery_builtinboston.requests.get") as mock_get:
            with pytest.raises(_BudgetExceeded):
                _fetch_apply_url("https://bib.com/job/1", budget)
        mock_get.assert_not_called()

    def test_budget_exceeded_during_retry_raises(self):
        # cap=1: initial request made (status 429), retry needs slot 2 → raises before retry
        budget = _Budget(cap=1)
        with patch(
            "scrapers.discovery_builtinboston.requests.get",
            return_value=self._429_resp(),
        ), patch("scrapers.discovery_builtinboston.time.sleep"):
            with pytest.raises(_BudgetExceeded):
                _fetch_apply_url("https://bib.com/job/1", budget)
        assert budget.count == 1  # first request consumed; retry was blocked


# ---------------------------------------------------------------------------
# run_rotation — cursor persistence tests
# ---------------------------------------------------------------------------

class TestRotationCursor:
    def _minimal_run(self, queue: list, tmp_path: Path) -> None:
        """Run rotation with an empty listing page (zero candidates after filter)."""
        empty_resp = MagicMock(status_code=200, text="<html></html>")
        empty_resp.raise_for_status = MagicMock()
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=empty_resp), \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(queue)

    def test_cursor_defaults_to_zero_when_file_absent(self, monkeypatch, tmp_path):
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)
        # No file → loads 0, uses queue[0], saves next=1
        self._minimal_run(["Alpha", "Beta", "Gamma"], tmp_path)
        assert _j.loads(cursor_file.read_text())["cursor"] == 1

    def test_cursor_advances_after_run(self, monkeypatch, tmp_path):
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)
        cursor_file.write_text(_j.dumps({"cursor": 5}))
        self._minimal_run([f"kw{i}" for i in range(24)], tmp_path)
        assert _j.loads(cursor_file.read_text())["cursor"] == 6

    def test_cursor_wraps_from_last_slot_to_zero(self, monkeypatch, tmp_path):
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)
        cursor_file.write_text(_j.dumps({"cursor": 23}))
        self._minimal_run([f"kw{i}" for i in range(24)], tmp_path)
        assert _j.loads(cursor_file.read_text())["cursor"] == 0

    def test_cursor_advances_even_on_403_listing(self, monkeypatch, tmp_path):
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)
        cursor_file.write_text(_j.dumps({"cursor": 7}))
        resp_403 = MagicMock(status_code=403)
        queue = [f"kw{i}" for i in range(24)]
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=resp_403):
            run_rotation(queue)
        assert _j.loads(cursor_file.read_text())["cursor"] == 8


# ---------------------------------------------------------------------------
# run_rotation — budget cap + monitor path tests
# ---------------------------------------------------------------------------

class TestRunRotationBudget:
    """Budget cap behavior: stop at 20, write remaining unseen cards to _write_monitor_card."""

    def _make_candidates(self, n: int) -> list[BIBCard]:
        return [
            _make_card(
                company_name=f"Company{i}",
                job_id=i,
                detail_url=f"https://www.builtinboston.com/job/role/{i}",
            )
            for i in range(n)
        ]

    def _listing_resp_empty(self) -> MagicMock:
        resp = MagicMock(status_code=200, text="<html/>")
        resp.raise_for_status = MagicMock()
        return resp

    def test_budget_cap_halts_mid_keyword(self, monkeypatch, tmp_path):
        """With 25 candidates and cap=20, the 21st call raises _BudgetExceeded."""
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        candidates = self._make_candidates(25)
        call_count = [0]

        def mock_fetch(url, budget):
            call_count[0] += 1
            if call_count[0] > 20:
                raise _BudgetExceeded()
            return f"https://lever.co/company/job/{call_count[0]}"

        with patch("scrapers.discovery_builtinboston.requests.get", return_value=self._listing_resp_empty()), \
             patch("scrapers.discovery_builtinboston._parse_listing_page", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._filter_cards", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", side_effect=mock_fetch), \
             patch("scrapers.discovery_builtinboston._write_monitor_card") as mock_monitor, \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"])

        # 20 successes + 1 that raised = 21 total calls to mock_fetch
        assert call_count[0] == 21
        # Cards at index 20-24 (5 cards) go to monitor
        assert mock_monitor.call_count == 5

    def test_budget_cap_monitor_receives_correct_cards(self, monkeypatch, tmp_path):
        """Cards written to monitor are the ones that didn't get a detail fetch."""
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        candidates = self._make_candidates(5)
        call_count = [0]

        def mock_fetch(url, budget):
            call_count[0] += 1
            if call_count[0] > 3:
                raise _BudgetExceeded()
            return "https://lever.co/company/job/1"

        captured_cards = []
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=self._listing_resp_empty()), \
             patch("scrapers.discovery_builtinboston._parse_listing_page", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._filter_cards", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", side_effect=mock_fetch), \
             patch("scrapers.discovery_builtinboston._write_monitor_card", side_effect=lambda c, dry: captured_cards.append(c)), \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"])

        # cap triggers on call 4 (card index 3) → cards 3 and 4 go to monitor
        assert len(captured_cards) == 2
        assert captured_cards[0].company_name == "Company3"
        assert captured_cards[1].company_name == "Company4"

    def test_budget_cap_monitor_fields_match_card(self, monkeypatch, tmp_path):
        """_write_monitor_card receives the original BIBCard with all fields intact."""
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", tmp_path / "cursor.json")
        target_card = _make_card(
            title="Solutions Engineer",
            company_name="TargetCo",
            detail_url="https://www.builtinboston.com/job/se/12345",
            salary_text="90K-120K Annually",
            seniority_text="Senior level",
        )
        candidates = [_make_card(company_name="First", detail_url="https://bib.com/job/1"), target_card]

        def mock_fetch(url, budget):
            if "12345" in url:
                raise _BudgetExceeded()
            return "https://lever.co/first/job/1"

        captured = []
        with patch("scrapers.discovery_builtinboston.requests.get", return_value=self._listing_resp_empty()), \
             patch("scrapers.discovery_builtinboston._parse_listing_page", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._filter_cards", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", side_effect=mock_fetch), \
             patch("scrapers.discovery_builtinboston._write_monitor_card", side_effect=lambda c, dry: captured.append(c)), \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation(["Solutions Engineer"])

        assert len(captured) == 1
        c = captured[0]
        assert c.title == "Solutions Engineer"
        assert c.company_name == "TargetCo"
        assert c.detail_url == "https://www.builtinboston.com/job/se/12345"
        assert c.salary_text == "90K-120K Annually"
        assert c.seniority_text == "Senior level"

    def test_cursor_advances_after_budget_cap(self, monkeypatch, tmp_path):
        """Cursor advances to next slot even when budget cap hits mid-keyword."""
        import json as _j
        cursor_file = tmp_path / "cursor.json"
        monkeypatch.setattr("scrapers.discovery_builtinboston._CURSOR_FILE", cursor_file)
        cursor_file.write_text(_j.dumps({"cursor": 10}))
        candidates = self._make_candidates(5)

        def mock_fetch(url, budget):
            raise _BudgetExceeded()

        with patch("scrapers.discovery_builtinboston.requests.get", return_value=self._listing_resp_empty()), \
             patch("scrapers.discovery_builtinboston._parse_listing_page", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._filter_cards", return_value=candidates), \
             patch("scrapers.discovery_builtinboston._fetch_apply_url", side_effect=mock_fetch), \
             patch("scrapers.discovery_builtinboston._write_monitor_card"), \
             patch("scrapers.discovery_builtinboston.time.sleep"):
            run_rotation([f"kw{i}" for i in range(24)])

        assert _j.loads(cursor_file.read_text())["cursor"] == 11


# ---------------------------------------------------------------------------
# Queue structure — weighting verification
# ---------------------------------------------------------------------------

class TestQueueStructure:
    def test_queue_length_is_24(self):
        assert len(BUILTINBOSTON_ROTATION_QUEUE) == 24

    def test_keep_tier_titles_appear_exactly_twice(self):
        for title in BUILTINBOSTON_TITLES["keep"]:
            count = BUILTINBOSTON_ROTATION_QUEUE.count(title)
            assert count == 2, f"'{title}' appears {count} times, expected 2"

    def test_borderline_tier_titles_appear_exactly_once(self):
        for title in BUILTINBOSTON_TITLES["borderline"]:
            count = BUILTINBOSTON_ROTATION_QUEUE.count(title)
            assert count == 1, f"'{title}' appears {count} times, expected 1"

    def test_keep_tier_has_10_titles(self):
        assert len(BUILTINBOSTON_TITLES["keep"]) == 10

    def test_borderline_tier_has_4_titles(self):
        assert len(BUILTINBOSTON_TITLES["borderline"]) == 4

    def test_all_queue_titles_are_in_one_tier(self):
        all_tier_titles = (
            set(BUILTINBOSTON_TITLES["keep"]) | set(BUILTINBOSTON_TITLES["borderline"])
        )
        for title in BUILTINBOSTON_ROTATION_QUEUE:
            assert title in all_tier_titles, f"'{title}' in queue but not in any tier"

    def test_customer_solutions_engineer_not_in_queue(self):
        # Dropped: already caught by "Solutions Engineer" search
        assert "Customer Solutions Engineer" not in BUILTINBOSTON_ROTATION_QUEUE
