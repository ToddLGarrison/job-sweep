import pytest
from red_flag_detector import check_red_flags, RedFlag


def codes(flags: list[RedFlag]) -> set[str]:
    return {f.code for f in flags}


# --- TRAVEL_HEAVY ---

class TestTravelHeavy:
    def test_75_percent_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "requires 75% travel"))

    def test_50_percent_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "up to 50% travel"))

    def test_heavy_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "heavy travel required"))

    def test_extensive_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "extensive travel to customer sites"))

    def test_frequent_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "frequent travel is expected"))

    def test_significant_travel(self):
        assert "TRAVEL_HEAVY" in codes(check_red_flags("", "significant travel required"))

    def test_occasional_travel_not_flagged(self):
        assert "TRAVEL_HEAVY" not in codes(check_red_flags("", "occasional travel required"))

    def test_minimal_travel_not_flagged(self):
        assert "TRAVEL_HEAVY" not in codes(check_red_flags("", "minimal travel"))

    def test_some_travel_not_flagged(self):
        assert "TRAVEL_HEAVY" not in codes(check_red_flags("", "some travel may be required"))

    def test_post_sales_75_percent_not_flagged(self):
        # "75% of time on post-sales activities" should NOT be a travel flag
        assert "TRAVEL_HEAVY" not in codes(check_red_flags("", "spend 75% of your time on post-sales activities"))


# --- QUOTA_CARRYING ---

class TestQuotaCarrying:
    def test_quota_carrying(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "this is a quota-carrying role"))

    def test_carry_a_quota(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "you will carry a quota"))

    def test_sales_quota(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "responsible for meeting sales quota"))

    def test_base_plus_commission(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "base + commission structure"))

    def test_base_plus_commission_spelled_out(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "base plus commission structure"))

    def test_uncapped_commission(self):
        assert "QUOTA_CARRYING" in codes(check_red_flags("", "uncapped commission potential"))

    def test_variable_comp_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "variable compensation included"))

    def test_ote_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "OTE $150,000"))

    def test_on_target_earnings_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "on-target earnings of $120k"))

    def test_commission_based_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "commission-based compensation"))

    def test_closing_deals_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "responsible for closing deals with enterprise clients"))

    def test_comp_in_range_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "compensation: $100k-$130k annually"))

    def test_post_sales_mention_not_flagged(self):
        assert "QUOTA_CARRYING" not in codes(check_red_flags("", "work with post-sales team to drive adoption"))


# --- OUTBOUND_SALES ---

class TestOutboundSales:
    def test_cold_calling(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "experience with cold-calling prospects"))

    def test_cold_calls(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "make 50 cold calls per day"))

    def test_outbound_prospecting(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "outbound prospecting to build pipeline"))

    def test_lead_generation(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "responsible for lead generation"))

    def test_pipeline_generation(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "pipeline generation from scratch"))

    def test_hunter_mentality(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "we want someone with a hunter mentality"))

    def test_new_logo(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "focus on new logo acquisition"))

    def test_sdr_title_in_description(self):
        assert "OUTBOUND_SALES" in codes(check_red_flags("", "partner with SDR team to qualify leads"))

    def test_inbound_leads_not_flagged(self):
        assert "OUTBOUND_SALES" not in codes(check_red_flags("", "respond to inbound leads from marketing"))

    def test_pipeline_management_not_flagged(self):
        # Managing existing pipeline ≠ outbound generation
        assert "OUTBOUND_SALES" not in codes(check_red_flags("", "manage pipeline of existing opportunities"))


# --- SUPPORT_ONLY ---

class TestSupportOnly:
    def test_tier_1_support(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "tier-1 support agent role"))

    def test_tier1_support(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "tier1 support tickets"))

    def test_help_desk(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "help desk technician"))

    def test_helpdesk(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "helpdesk operations"))

    def test_ticket_based(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "ticket-based customer service"))

    def test_l1_support(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "L1 support engineer"))

    def test_call_center(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "call center environment"))

    def test_inbound_support_calls(self):
        assert "SUPPORT_ONLY" in codes(check_red_flags("", "handle inbound support calls"))

    def test_technical_support_engineer_not_flagged(self):
        # Generic "technical support" without tier-1/helpdesk signals should not flag
        assert "SUPPORT_ONLY" not in codes(check_red_flags("Technical Support Engineer", "resolve complex technical issues for enterprise customers"))

    def test_customer_success_not_flagged(self):
        assert "SUPPORT_ONLY" not in codes(check_red_flags("Customer Success Manager", "drive adoption and expansion"))


# --- HARDWARE_ONLY ---

class TestHardwareOnly:
    def test_physical_installation(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "physical installation of network equipment"))

    def test_onsite_installation(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "on-site installation at customer premises"))

    def test_hardware_deployment(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "hardware deployment and configuration"))

    def test_racking_and_stacking(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "racking and stacking servers"))

    def test_data_center_technician(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "data center technician role"))

    def test_field_technician(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("Field Technician", ""))

    def test_break_fix(self):
        assert "HARDWARE_ONLY" in codes(check_red_flags("", "break-fix support for hardware"))

    def test_hardware_experience_not_flagged(self):
        # Mentioning hardware familiarity ≠ hardware-only role
        assert "HARDWARE_ONLY" not in codes(check_red_flags("Solutions Engineer", "familiarity with hardware and software solutions is a plus"))


# --- LEADERSHIP_REQ ---

class TestLeadershipReq:
    def test_manage_a_team(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "you will manage a team of 5 engineers"))

    def test_direct_reports(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "role has 3 direct reports"))

    def test_people_manager(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "this is a people manager role"))

    def test_management_experience_required(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "management experience required"))

    def test_years_of_management(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "3+ years of management experience"))

    def test_experience_managing_team(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "experience managing a team of engineers"))

    def test_prior_management(self):
        assert "LEADERSHIP_REQ" in codes(check_red_flags("", "prior management experience preferred"))

    def test_individual_contributor_not_flagged(self):
        assert "LEADERSHIP_REQ" not in codes(check_red_flags("", "individual contributor role with growth potential"))

    def test_cross_functional_collaboration_not_flagged(self):
        assert "LEADERSHIP_REQ" not in codes(check_red_flags("", "work cross-functionally with product and engineering teams"))


# --- Multi-flag scenarios ---

class TestMultiFlag:
    def test_two_flags_detected(self):
        desc = "quota-carrying role with 75% travel required"
        result = codes(check_red_flags("", desc))
        assert "QUOTA_CARRYING" in result
        assert "TRAVEL_HEAVY" in result

    def test_three_flags_detected(self):
        desc = "cold calling, quota-carrying, tier-1 support tickets"
        result = codes(check_red_flags("", desc))
        assert "OUTBOUND_SALES" in result
        assert "QUOTA_CARRYING" in result
        assert "SUPPORT_ONLY" in result

    def test_clean_se_jd_no_flags(self):
        desc = (
            "As a Solutions Engineer you will partner with Account Executives to run technical "
            "discovery, deliver product demos, and guide customers through proof-of-concept. "
            "You will work closely with the post-sales team to ensure smooth handoffs. "
            "Occasional travel to customer sites expected. Compensation: $130k-$155k base."
        )
        result = codes(check_red_flags("Solutions Engineer", desc))
        assert result == set()

    def test_title_scanned_for_flags(self):
        # Title alone can trigger flag
        result = codes(check_red_flags("Field Technician", ""))
        assert "HARDWARE_ONLY" in result
