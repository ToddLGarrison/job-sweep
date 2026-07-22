import pytest
from geo_filter import (
    check_description_geo,
    is_title_geo_excluded,
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


# --- is_title_geo_excluded ---

class TestIsTitleGeoExcluded:
    # Should be excluded
    def test_emea_excluded(self):
        assert is_title_geo_excluded("Customer Success Engineer, EMEA") is True

    def test_anz_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - ANZ") is True

    def test_japan_excluded(self):
        assert is_title_geo_excluded("Technical Account Manager, Japan") is True

    def test_italy_excluded(self):
        assert is_title_geo_excluded("Solutions Consultant, Italy") is True

    def test_france_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - France") is True

    def test_apac_excluded(self):
        assert is_title_geo_excluded("Customer Success Manager - APAC") is True

    def test_latam_excluded(self):
        assert is_title_geo_excluded("Enterprise Solutions Engineer, LATAM") is True

    def test_dach_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - DACH") is True

    def test_uki_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer, UKI") is True

    def test_uk_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - UK") is True

    def test_nordics_excluded(self):
        assert is_title_geo_excluded("Customer Success Manager, Nordics") is True

    def test_germany_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - Germany") is True

    def test_australia_excluded(self):
        assert is_title_geo_excluded("Technical Account Manager, Australia") is True

    def test_singapore_excluded(self):
        assert is_title_geo_excluded("Customer Engineer - Singapore") is True

    def test_london_excluded(self):
        assert is_title_geo_excluded("Solutions Architect, London") is True

    def test_toronto_excluded(self):
        assert is_title_geo_excluded("Customer Success Manager - Toronto") is True

    def test_case_insensitive(self):
        assert is_title_geo_excluded("solutions engineer, emea") is True

    # Should NOT be excluded
    def test_southeast_not_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - Southeast") is False

    def test_west_not_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - West") is False

    def test_commercial_not_excluded(self):
        assert is_title_geo_excluded("Solutions Architect, Commercial") is False

    def test_plain_csm_not_excluded(self):
        assert is_title_geo_excluded("Customer Success Manager") is False

    def test_bridge_not_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer, Bridge") is False

    def test_dc_virginia_not_excluded(self):
        assert is_title_geo_excluded("Public Sector Solutions Architect - D.C. / Northern Virginia") is False

    def test_expansion_not_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - Commercial (Expansion Sales)") is False

    def test_enterprise_not_excluded(self):
        assert is_title_geo_excluded("Enterprise Customer Success Manager") is False

    # ISO-3166-1 alpha-3 codes
    def test_aut_in_parenthetical_excluded(self):
        assert is_title_geo_excluded("Regional Sales Engineer (Remote, AUT)") is True

    def test_aus_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - AUS") is True

    def test_can_excluded(self):
        assert is_title_geo_excluded("Technical Account Manager (CAN)") is True

    def test_gbr_excluded(self):
        assert is_title_geo_excluded("Solutions Architect - GBR") is True

    def test_deu_excluded(self):
        assert is_title_geo_excluded("Customer Success Engineer, DEU") is True

    def test_ind_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - IND") is True

    def test_fra_excluded(self):
        assert is_title_geo_excluded("Technical Account Manager, FRA") is True

    def test_jpn_excluded(self):
        assert is_title_geo_excluded("Solutions Consultant - JPN") is True

    def test_sgp_excluded(self):
        assert is_title_geo_excluded("Customer Engineer - SGP") is True

    def test_bra_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer (BRA)") is True

    def test_mex_excluded(self):
        assert is_title_geo_excluded("Technical Account Manager - MEX") is True

    def test_irl_excluded(self):
        assert is_title_geo_excluded("Solutions Architect, IRL") is True

    def test_nld_excluded(self):
        assert is_title_geo_excluded("Customer Success Engineer - NLD") is True

    def test_che_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - CHE") is True

    def test_alpha3_case_insensitive(self):
        assert is_title_geo_excluded("Solutions Engineer (remote, aut)") is True

    # Word-boundary guard: common substrings must not false-positive
    def test_candidate_not_excluded(self):
        assert is_title_geo_excluded("Senior Candidate Experience Manager") is False

    def test_framework_not_excluded(self):
        assert is_title_geo_excluded("Solutions Engineer - Framework Specialist") is False

    def test_branch_not_excluded(self):
        assert is_title_geo_excluded("Implementation Consultant - Branch Banking") is False

    def test_independent_not_excluded(self):
        assert is_title_geo_excluded("Independent Software Vendor Specialist") is False


# --- is_us_or_remote: Indian city + state-code edge cases ---

class TestIsUsOrRemoteIndianCities:
    def test_hyderabad_in_rejected(self):
        assert is_us_or_remote("Hyderabad IN") is False

    def test_pune_mh_rejected(self):
        assert is_us_or_remote("Pune MH") is False

    def test_chennai_tn_rejected(self):
        assert is_us_or_remote("Chennai TN") is False

    def test_noida_rejected(self):
        assert is_us_or_remote("Noida") is False

    def test_gurgaon_rejected(self):
        assert is_us_or_remote("Gurgaon") is False

    def test_gurugram_rejected(self):
        assert is_us_or_remote("Gurugram") is False

    def test_karachi_rejected(self):
        assert is_us_or_remote("Karachi") is False

    def test_dhaka_rejected(self):
        assert is_us_or_remote("Dhaka") is False

    def test_colombo_rejected(self):
        assert is_us_or_remote("Colombo") is False

    def test_ho_chi_minh_rejected(self):
        assert is_us_or_remote("Ho Chi Minh City") is False

    def test_new_york_ny_still_passes(self):
        assert is_us_or_remote("New York NY") is True

    def test_austin_tx_still_passes(self):
        assert is_us_or_remote("Austin TX") is True

    def test_boston_ma_still_passes(self):
        assert is_us_or_remote("Boston MA") is True

    def test_remote_still_passes(self):
        assert is_us_or_remote("Remote") is True

    def test_empty_still_passes(self):
        assert is_us_or_remote("") is True


# --- check_description_geo ---

class TestCheckDescriptionGeo:
    def test_based_in_hyderabad_office(self):
        assert check_description_geo("This role is based in our Hyderabad office") is True

    def test_located_in_singapore(self):
        assert check_description_geo("Must be located in Singapore") is True

    def test_our_pune_office(self):
        assert check_description_geo("Our Pune office is growing") is True

    def test_based_in_india(self):
        assert check_description_geo("This position is based in India") is True

    def test_working_from_london(self):
        assert check_description_geo("Working from our London headquarters") is True

    def test_this_role_is_in_germany(self):
        assert check_description_geo("This role is in Germany") is True

    def test_based_in_new_york_not_flagged(self):
        assert check_description_geo("Based in New York, NY") is False

    def test_remote_role_us_not_flagged(self):
        assert check_description_geo("Remote role based in the US") is False

    def test_no_geo_signal_not_flagged(self):
        assert check_description_geo("No geo signal here") is False

    def test_empty_string_not_flagged(self):
        assert check_description_geo("") is False

    def test_generic_office_mention_not_flagged(self):
        assert check_description_geo("You will work closely with our sales team") is False
