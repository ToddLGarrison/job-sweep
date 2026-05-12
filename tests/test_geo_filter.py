import pytest
from geo_filter import (
    is_us_or_remote,
    location_from_greenhouse,
    location_from_lever,
    location_from_ashby,
)


# --- is_us_or_remote ---

class TestIsUsOrRemote:
    # Empty / unknown
    def test_empty_string_passes(self):
        assert is_us_or_remote("") is True

    def test_whitespace_only_passes(self):
        assert is_us_or_remote("   ") is True

    # Remote signals
    def test_remote_passes(self):
        assert is_us_or_remote("Remote") is True

    def test_remote_lowercase_passes(self):
        assert is_us_or_remote("remote") is True

    def test_us_remote_passes(self):
        assert is_us_or_remote("US Remote") is True

    def test_work_from_home_passes(self):
        assert is_us_or_remote("Work From Home") is True

    def test_distributed_passes(self):
        assert is_us_or_remote("Distributed") is True

    # US cities + state abbreviations
    def test_san_francisco_ca_passes(self):
        assert is_us_or_remote("San Francisco, CA") is True

    def test_new_york_ny_passes(self):
        assert is_us_or_remote("New York, NY") is True

    def test_austin_tx_passes(self):
        assert is_us_or_remote("Austin, TX") is True

    def test_seattle_wa_passes(self):
        assert is_us_or_remote("Seattle, WA") is True

    def test_chicago_il_passes(self):
        assert is_us_or_remote("Chicago, IL") is True

    def test_boston_ma_passes(self):
        assert is_us_or_remote("Boston, MA") is True

    def test_denver_co_passes(self):
        assert is_us_or_remote("Denver, CO") is True

    # Full US state names
    def test_full_state_california_passes(self):
        assert is_us_or_remote("California") is True

    def test_full_state_texas_passes(self):
        assert is_us_or_remote("Texas") is True

    def test_united_states_passes(self):
        assert is_us_or_remote("United States") is True

    # Tricky US cities that share names with foreign places
    def test_vancouver_wa_passes(self):
        assert is_us_or_remote("Vancouver, WA") is True

    def test_paris_tx_passes(self):
        assert is_us_or_remote("Paris, TX") is True

    # Clear non-US → reject
    def test_london_uk_rejected(self):
        assert is_us_or_remote("London, UK") is False

    def test_toronto_ontario_rejected(self):
        assert is_us_or_remote("Toronto, Ontario") is False

    def test_canada_rejected(self):
        assert is_us_or_remote("Canada") is False

    def test_vancouver_bc_rejected(self):
        assert is_us_or_remote("Vancouver, BC") is False

    def test_paris_france_rejected(self):
        assert is_us_or_remote("Paris, France") is False

    def test_berlin_germany_rejected(self):
        assert is_us_or_remote("Berlin, Germany") is False

    def test_sydney_australia_rejected(self):
        assert is_us_or_remote("Sydney, Australia") is False

    def test_emea_rejected(self):
        assert is_us_or_remote("EMEA") is False

    def test_apac_rejected(self):
        assert is_us_or_remote("APAC") is False

    def test_latam_rejected(self):
        assert is_us_or_remote("LATAM") is False

    def test_singapore_rejected(self):
        assert is_us_or_remote("Singapore") is False

    def test_europe_rejected(self):
        assert is_us_or_remote("Europe") is False

    def test_amsterdam_rejected(self):
        assert is_us_or_remote("Amsterdam, Netherlands") is False

    def test_british_columbia_rejected(self):
        assert is_us_or_remote("British Columbia") is False

    # Province abbreviation after comma
    def test_city_bc_province_rejected(self):
        assert is_us_or_remote("Burnaby, BC") is False

    def test_city_on_province_rejected(self):
        assert is_us_or_remote("Mississauga, ON") is False


# --- location_from_greenhouse ---

class TestLocationFromGreenhouse:
    def test_location_dict(self):
        job = {"location": {"name": "San Francisco, CA"}}
        assert location_from_greenhouse(job) == "San Francisco, CA"

    def test_location_dict_empty(self):
        job = {"location": {"name": ""}}
        assert location_from_greenhouse(job) == ""

    def test_location_string(self):
        job = {"location": "New York, NY"}
        assert location_from_greenhouse(job) == "New York, NY"

    def test_offices_fallback(self):
        job = {"offices": [{"name": "Austin, TX"}]}
        assert location_from_greenhouse(job) == "Austin, TX"

    def test_offices_multiple(self):
        job = {"offices": [{"name": "Austin, TX"}, {"name": "Remote"}]}
        assert location_from_greenhouse(job) == "Austin, TX, Remote"

    def test_missing_location(self):
        job = {}
        assert location_from_greenhouse(job) == ""


# --- location_from_lever ---

class TestLocationFromLever:
    def test_categories_location(self):
        job = {"categories": {"location": "San Francisco, CA"}}
        assert location_from_lever(job) == "San Francisco, CA"

    def test_remote_workplace_type(self):
        job = {"categories": {}, "workplaceType": "remote"}
        assert location_from_lever(job) == "Remote"

    def test_non_remote_workplace_type_ignored(self):
        job = {"categories": {}, "workplaceType": "onsite"}
        assert location_from_lever(job) == ""

    def test_empty_categories(self):
        job = {"categories": {}}
        assert location_from_lever(job) == ""

    def test_missing_everything(self):
        job = {}
        assert location_from_lever(job) == ""


# --- location_from_ashby ---

class TestLocationFromAshby:
    def test_location_name_string(self):
        job = {"locationName": "New York, NY"}
        assert location_from_ashby(job) == "New York, NY"

    def test_location_dict(self):
        job = {"location": {"name": "Remote"}}
        assert location_from_ashby(job) == "Remote"

    def test_location_string_fallback(self):
        job = {"location": "Boston, MA"}
        assert location_from_ashby(job) == "Boston, MA"

    def test_empty(self):
        job = {}
        assert location_from_ashby(job) == ""
