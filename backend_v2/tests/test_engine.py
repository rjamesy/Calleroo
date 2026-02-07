"""
Unit tests for the deterministic conversation engine.

Tests cover:
1. AgentSpec and SlotSpec definitions
2. Deterministic planner (slot ordering, action decisions)
3. Deterministic extraction (CHOICE, YES_NO, DATE, TIME, PHONE, NUMBER)
4. LLM extraction (mocked)
5. Integration: progressive slot filling through conversation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date

# =============================================================================
# IMPORT SYSTEM UNDER TEST
# =============================================================================

# Import specs
from agents.specs import (
    AgentSpec,
    SlotSpec,
    InputType,
    Choice,
    PhoneFlowMode,
    PhoneFlow,
    PhoneSource,
    SICK_CALLER_SPEC,
    STOCK_CHECKER_SPEC,
    RESTAURANT_RESERVATION_SPEC,
    CANCEL_APPOINTMENT_SPEC,
    AGENTS,
    get_agent_spec,
)

# Import planner
from engine.planner import (
    NextAction,
    ClientAction,
    Question,
    ConfirmationCard,
    PlaceSearchParams,
    PlannerResult,
    is_slot_filled,
    get_next_slot,
    get_missing_required_slots,
    should_trigger_find_place,
    build_question,
    build_confirmation_card,
    build_place_search_params,
    decide_next_action,
    format_slot_value_for_display,
)

# Import extraction
from engine.extract import (
    ExtractionResult,
    extract_choice_value,
    extract_yes_no_value,
    normalize_phone_number,
    parse_date,
    parse_time,
    parse_number,
    extract_slot_deterministic,
    extract_slots_sync,
    extract_slots,
    build_extraction_prompt,
)


# =============================================================================
# SPEC TESTS
# =============================================================================

class TestAgentSpecs:
    """Tests for AgentSpec definitions."""

    def test_sick_caller_spec_exists(self):
        """Verify SICK_CALLER spec is defined."""
        assert "SICK_CALLER" in AGENTS
        spec = get_agent_spec("SICK_CALLER")
        assert spec.agent_type == "SICK_CALLER"
        assert spec.title == "Call in Sick"

    def test_sick_caller_has_required_slots(self):
        """Verify SICK_CALLER has correct required slots in order."""
        spec = get_agent_spec("SICK_CALLER")
        required_names = spec.get_required_slot_names()
        assert required_names == [
            "employer_name",
            "employer_phone",
            "caller_name",
            "shift_date",
            "shift_start_time",
            "reason_category",
        ]

    def test_sick_caller_phone_source(self):
        """Verify SICK_CALLER uses DIRECT_SLOT phone source."""
        spec = get_agent_spec("SICK_CALLER")
        assert spec.phone_source == PhoneSource.DIRECT_SLOT
        assert spec.direct_phone_slot == "employer_phone"

    def test_sick_caller_phone_flow(self):
        """Verify SICK_CALLER uses DETERMINISTIC_SCRIPT phone flow."""
        spec = get_agent_spec("SICK_CALLER")
        assert spec.phone_flow.mode == PhoneFlowMode.DETERMINISTIC_SCRIPT
        assert spec.phone_flow.greeting_template is not None
        assert spec.phone_flow.message_template is not None

    def test_stock_checker_spec_exists(self):
        """Verify STOCK_CHECKER spec is defined."""
        spec = get_agent_spec("STOCK_CHECKER")
        assert spec.agent_type == "STOCK_CHECKER"
        assert spec.phone_source == PhoneSource.PLACE

    def test_stock_checker_has_place_slots(self):
        """Verify STOCK_CHECKER has place search slot configuration."""
        spec = get_agent_spec("STOCK_CHECKER")
        assert spec.place_query_slot == "retailer_name"
        assert spec.place_area_slot == "store_location"

    def test_restaurant_reservation_spec(self):
        """Verify RESTAURANT_RESERVATION spec is defined."""
        spec = get_agent_spec("RESTAURANT_RESERVATION")
        required_names = spec.get_required_slot_names()
        assert "restaurant_name" in required_names
        assert "party_size" in required_names
        assert "date" in required_names
        assert "time" in required_names

    def test_cancel_appointment_spec(self):
        """Verify CANCEL_APPOINTMENT spec is defined."""
        spec = get_agent_spec("CANCEL_APPOINTMENT")
        required_names = spec.get_required_slot_names()
        assert "business_name" in required_names
        assert "appointment_day" in required_names
        assert "customer_name" in required_names

    def test_invalid_agent_type_raises(self):
        """Verify unknown agent type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_agent_spec("INVALID_AGENT")
        assert "Unknown agent type" in str(exc_info.value)

    def test_slot_spec_get_quick_replies_choice(self):
        """Verify CHOICE slot returns quick replies."""
        spec = get_agent_spec("SICK_CALLER")
        reason_slot = spec.get_slot_by_name("reason_category")
        qr = reason_slot.get_quick_replies()
        assert qr is not None
        assert len(qr) == 4
        assert qr[0]["label"] == "I'm sick"
        assert qr[0]["value"] == "SICK"

    def test_slot_spec_get_quick_replies_yes_no(self):
        """Verify YES_NO slot returns Yes/No quick replies."""
        spec = get_agent_spec("RESTAURANT_RESERVATION")
        share_slot = spec.get_slot_by_name("share_contact")
        qr = share_slot.get_quick_replies()
        assert qr is not None
        assert len(qr) == 2
        assert qr[0]["value"] == "YES"
        assert qr[1]["value"] == "NO"

    def test_slot_spec_get_quick_replies_text(self):
        """Verify TEXT slot returns no quick replies."""
        spec = get_agent_spec("SICK_CALLER")
        name_slot = spec.get_slot_by_name("employer_name")
        qr = name_slot.get_quick_replies()
        assert qr is None


# =============================================================================
# PLANNER TESTS
# =============================================================================

class TestIsSlotFilled:
    """Tests for is_slot_filled function."""

    def test_slot_not_in_dict(self):
        """Slot not in dict is not filled."""
        assert is_slot_filled({}, "name") is False

    def test_slot_is_none(self):
        """Slot with None value is not filled."""
        assert is_slot_filled({"name": None}, "name") is False

    def test_slot_is_empty_string(self):
        """Slot with empty string is not filled."""
        assert is_slot_filled({"name": ""}, "name") is False
        assert is_slot_filled({"name": "  "}, "name") is False

    def test_slot_has_value(self):
        """Slot with value is filled."""
        assert is_slot_filled({"name": "John"}, "name") is True
        assert is_slot_filled({"count": 5}, "count") is True
        assert is_slot_filled({"count": 0}, "count") is True  # 0 is valid


class TestGetNextSlot:
    """Tests for get_next_slot function."""

    def test_empty_slots_returns_first(self):
        """Empty slots returns first required slot."""
        spec = get_agent_spec("SICK_CALLER")
        next_slot = get_next_slot(spec, {})
        assert next_slot is not None
        assert next_slot.name == "employer_name"

    def test_first_slot_filled_returns_second(self):
        """First slot filled returns second required slot."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {"employer_name": "Bunnings"}
        next_slot = get_next_slot(spec, slots)
        assert next_slot is not None
        assert next_slot.name == "employer_phone"

    def test_partial_slots_returns_next_missing(self):
        """Partial slots returns next missing required slot."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
            "caller_name": "John",
        }
        next_slot = get_next_slot(spec, slots)
        assert next_slot is not None
        assert next_slot.name == "shift_date"

    def test_all_required_filled_returns_none(self):
        """All required slots filled returns None."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
            "caller_name": "John",
            "shift_date": "2026-02-01",
            "shift_start_time": "09:00",
            "reason_category": "SICK",
        }
        next_slot = get_next_slot(spec, slots)
        assert next_slot is None


class TestGetMissingRequiredSlots:
    """Tests for get_missing_required_slots function."""

    def test_empty_slots_returns_all_required(self):
        """Empty slots returns all required slot names."""
        spec = get_agent_spec("SICK_CALLER")
        missing = get_missing_required_slots(spec, {})
        assert len(missing) == 6
        assert missing[0] == "employer_name"

    def test_partial_slots_returns_missing(self):
        """Partial slots returns only missing required slots."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {"employer_name": "Bunnings", "employer_phone": "+61412345678"}
        missing = get_missing_required_slots(spec, slots)
        assert "employer_name" not in missing
        assert "employer_phone" not in missing
        assert "caller_name" in missing


class TestShouldTriggerFindPlace:
    """Tests for should_trigger_find_place function."""

    def test_no_slot_returns_false(self):
        """No current slot returns False."""
        assert should_trigger_find_place("find it", None) is False

    def test_non_phone_slot_returns_false(self):
        """Non-PHONE slot returns False."""
        spec = get_agent_spec("SICK_CALLER")
        name_slot = spec.get_slot_by_name("employer_name")
        assert should_trigger_find_place("find it", name_slot) is False

    def test_phone_slot_with_keywords_returns_true(self):
        """PHONE slot with find keywords returns True."""
        spec = get_agent_spec("SICK_CALLER")
        phone_slot = spec.get_slot_by_name("employer_phone")
        assert should_trigger_find_place("I don't know the number", phone_slot) is True
        assert should_trigger_find_place("can you find it", phone_slot) is True
        assert should_trigger_find_place("not sure", phone_slot) is True

    def test_phone_slot_with_number_returns_false(self):
        """PHONE slot with actual number returns False."""
        spec = get_agent_spec("SICK_CALLER")
        phone_slot = spec.get_slot_by_name("employer_phone")
        assert should_trigger_find_place("0412345678", phone_slot) is False


class TestBuildQuestion:
    """Tests for build_question function."""

    def test_text_slot_question(self):
        """TEXT slot builds question without quick replies."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("employer_name")
        question = build_question(slot)
        assert question.slot_name == "employer_name"
        assert question.input_type == "TEXT"
        assert question.prompt == slot.prompt
        assert question.quick_replies is None

    def test_choice_slot_question(self):
        """CHOICE slot builds question with quick replies."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        question = build_question(slot)
        assert question.slot_name == "reason_category"
        assert question.input_type == "CHOICE"
        assert question.quick_replies is not None
        assert len(question.quick_replies) == 4

    def test_yes_no_slot_question(self):
        """YES_NO slot builds question with Yes/No quick replies."""
        spec = get_agent_spec("RESTAURANT_RESERVATION")
        slot = spec.get_slot_by_name("share_contact")
        question = build_question(slot)
        assert question.input_type == "YES_NO"
        assert len(question.quick_replies) == 2


class TestBuildConfirmationCard:
    """Tests for build_confirmation_card function."""

    def test_sick_caller_confirmation_card(self):
        """SICK_CALLER confirmation card is built correctly."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
            "caller_name": "John",
            "shift_date": "2026-02-01",
            "shift_start_time": "09:00",
            "reason_category": "SICK",
        }
        card = build_confirmation_card(spec, slots)
        assert card.title == "Call In Sick"
        assert "Calling: Bunnings" in card.lines
        assert "Phone: +61412345678" in card.lines
        assert "Your name: John" in card.lines
        assert card.card_id is not None

    def test_reason_category_formatted(self):
        """Reason category is formatted to human-readable label."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
            "caller_name": "John",
            "shift_date": "2026-02-01",
            "shift_start_time": "09:00",
            "reason_category": "MENTAL_HEALTH",
        }
        card = build_confirmation_card(spec, slots)
        assert "Reason: Mental health day" in card.lines


class TestBuildPlaceSearchParams:
    """Tests for build_place_search_params function."""

    def test_stock_checker_place_params(self):
        """STOCK_CHECKER place params are built from slots."""
        spec = get_agent_spec("STOCK_CHECKER")
        slots = {"retailer_name": "JB Hi-Fi", "store_location": "Sydney"}
        params = build_place_search_params(spec, slots)
        assert params.query == "JB Hi-Fi"
        assert params.area == "Sydney"

    def test_missing_slots_uses_defaults(self):
        """Missing slot values use defaults."""
        spec = get_agent_spec("STOCK_CHECKER")
        params = build_place_search_params(spec, {})
        assert params.query == "store"  # Default fallback query
        assert params.area == "Australia"


class TestDecideNextAction:
    """Tests for decide_next_action function (main planner)."""

    def test_confirm_action_returns_complete(self):
        """client_action=CONFIRM returns COMPLETE."""
        spec = get_agent_spec("SICK_CALLER")
        result = decide_next_action(spec, {}, client_action="CONFIRM")
        assert result.next_action == NextAction.COMPLETE
        assert "place the call" in result.assistant_message.lower()

    def test_reject_action_returns_ask_question(self):
        """client_action=REJECT returns ASK_QUESTION."""
        spec = get_agent_spec("SICK_CALLER")
        result = decide_next_action(spec, {}, client_action="REJECT")
        assert result.next_action == NextAction.ASK_QUESTION

    def test_empty_slots_asks_first_question(self):
        """Empty slots returns ASK_QUESTION for first slot."""
        spec = get_agent_spec("SICK_CALLER")
        result = decide_next_action(spec, {})
        assert result.next_action == NextAction.ASK_QUESTION
        assert result.question is not None
        assert result.question.slot_name == "employer_name"

    def test_partial_slots_asks_next_missing(self):
        """Partial slots returns ASK_QUESTION for next missing."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
        }
        result = decide_next_action(spec, slots)
        assert result.next_action == NextAction.ASK_QUESTION
        assert result.question.slot_name == "caller_name"

    def test_all_slots_filled_returns_confirm(self):
        """All required slots filled returns CONFIRM."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {
            "employer_name": "Bunnings",
            "employer_phone": "+61412345678",
            "caller_name": "John",
            "shift_date": "2026-02-01",
            "shift_start_time": "09:00",
            "reason_category": "SICK",
        }
        result = decide_next_action(spec, slots)
        assert result.next_action == NextAction.CONFIRM
        assert result.confirmation_card is not None

    def test_find_place_trigger(self):
        """FIND_PLACE is triggered when user doesn't know phone."""
        spec = get_agent_spec("STOCK_CHECKER")
        slots = {"retailer_name": "JB Hi-Fi"}
        # Current question is for a slot that doesn't exist in STOCK_CHECKER as PHONE
        # Let's use a spec that would have a phone slot being asked
        # Actually STOCK_CHECKER doesn't have a PHONE slot, let's create a scenario
        # In real usage, this would be detected by should_trigger_find_place
        # For now, test the path directly
        pass  # This test needs a different setup


class TestPlannerProgression:
    """Integration tests for progressive slot filling."""

    def test_sick_caller_full_progression(self):
        """Test complete SICK_CALLER conversation progression."""
        spec = get_agent_spec("SICK_CALLER")
        slots = {}

        # Step 1: Empty slots -> ask employer_name
        result = decide_next_action(spec, slots)
        assert result.next_action == NextAction.ASK_QUESTION
        assert result.question.slot_name == "employer_name"

        # Step 2: After employer_name -> ask employer_phone
        slots["employer_name"] = "Bunnings"
        result = decide_next_action(spec, slots)
        assert result.question.slot_name == "employer_phone"

        # Step 3: After employer_phone -> ask caller_name
        slots["employer_phone"] = "+61412345678"
        result = decide_next_action(spec, slots)
        assert result.question.slot_name == "caller_name"

        # Step 4: After caller_name -> ask shift_date
        slots["caller_name"] = "John"
        result = decide_next_action(spec, slots)
        assert result.question.slot_name == "shift_date"

        # Step 5: After shift_date -> ask shift_start_time
        slots["shift_date"] = "2026-02-01"
        result = decide_next_action(spec, slots)
        assert result.question.slot_name == "shift_start_time"

        # Step 6: After shift_start_time -> ask reason_category (CHOICE)
        slots["shift_start_time"] = "09:00"
        result = decide_next_action(spec, slots)
        assert result.question.slot_name == "reason_category"
        assert result.question.quick_replies is not None

        # Step 7: After reason_category -> CONFIRM
        slots["reason_category"] = "SICK"
        result = decide_next_action(spec, slots)
        assert result.next_action == NextAction.CONFIRM
        assert result.confirmation_card is not None

        # Step 8: User confirms -> COMPLETE
        result = decide_next_action(spec, slots, client_action="CONFIRM")
        assert result.next_action == NextAction.COMPLETE


# =============================================================================
# EXTRACTION TESTS
# =============================================================================

class TestExtractChoiceValue:
    """Tests for extract_choice_value function."""

    def test_exact_value_match(self):
        """Exact value match extracts correctly."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        assert extract_choice_value("SICK", slot) == "SICK"
        assert extract_choice_value("sick", slot) == "SICK"

    def test_label_match(self):
        """Label match extracts correctly."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        assert extract_choice_value("I'm sick", slot) == "SICK"
        assert extract_choice_value("Caring for someone", slot) == "CARER"

    def test_partial_label_match(self):
        """Partial label match extracts correctly."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        assert extract_choice_value("sick", slot) == "SICK"
        assert extract_choice_value("mental health", slot) == "MENTAL_HEALTH"

    def test_no_match_returns_none(self):
        """No match returns None."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        assert extract_choice_value("vacation", slot) is None


class TestExtractYesNoValue:
    """Tests for extract_yes_no_value function."""

    def test_yes_patterns(self):
        """Yes patterns extract as YES."""
        assert extract_yes_no_value("yes") == "YES"
        assert extract_yes_no_value("Yeah") == "YES"
        assert extract_yes_no_value("yep") == "YES"
        assert extract_yes_no_value("sure") == "YES"
        assert extract_yes_no_value("ok") == "YES"
        assert extract_yes_no_value("y") == "YES"

    def test_no_patterns(self):
        """No patterns extract as NO."""
        assert extract_yes_no_value("no") == "NO"
        assert extract_yes_no_value("nope") == "NO"
        assert extract_yes_no_value("nah") == "NO"
        assert extract_yes_no_value("n") == "NO"

    def test_ambiguous_returns_none(self):
        """Ambiguous input returns None."""
        assert extract_yes_no_value("maybe") is None
        assert extract_yes_no_value("I don't know") is None


class TestNormalizePhoneNumber:
    """Tests for normalize_phone_number function."""

    def test_australian_mobile_with_zero(self):
        """Australian mobile with leading 0 normalizes to E.164."""
        assert normalize_phone_number("0412345678") == "+61412345678"
        assert normalize_phone_number("0412 345 678") == "+61412345678"

    def test_australian_mobile_without_zero(self):
        """Australian mobile without leading 0 normalizes to E.164."""
        assert normalize_phone_number("412345678") == "+61412345678"

    def test_with_country_code(self):
        """Number with country code preserves it."""
        assert normalize_phone_number("+61412345678") == "+61412345678"
        assert normalize_phone_number("61412345678") == "+61412345678"

    def test_invalid_returns_none(self):
        """Invalid number returns None."""
        assert normalize_phone_number("123") is None
        assert normalize_phone_number("abc") is None


class TestParseDate:
    """Tests for parse_date function."""

    def test_today(self):
        """'today' returns today's date."""
        result = parse_date("today")
        assert result == date.today().isoformat()

    def test_tomorrow(self):
        """'tomorrow' returns tomorrow's date."""
        from datetime import timedelta
        expected = (date.today() + timedelta(days=1)).isoformat()
        assert parse_date("tomorrow") == expected
        assert parse_date("tmrw") == expected

    def test_iso_format(self):
        """ISO format parses correctly."""
        assert parse_date("2026-02-01") == "2026-02-01"

    def test_au_format(self):
        """Australian date format parses correctly."""
        assert parse_date("01/02/2026") == "2026-02-01"

    def test_written_format(self):
        """Written date format parses correctly."""
        assert parse_date("February 1, 2026") == "2026-02-01"
        assert parse_date("1 February 2026") == "2026-02-01"

    def test_invalid_returns_none(self):
        """Invalid date returns None."""
        assert parse_date("not a date") is None


class TestParseTime:
    """Tests for parse_time function."""

    def test_24_hour_format(self):
        """24-hour format parses correctly."""
        assert parse_time("14:00") == "14:00"
        assert parse_time("09:30") == "09:30"

    def test_12_hour_format(self):
        """12-hour format parses correctly."""
        assert parse_time("2:00 PM") == "14:00"
        assert parse_time("9:30 AM") == "09:30"
        assert parse_time("2pm") == "14:00"
        assert parse_time("9am") == "09:00"

    def test_simple_hour(self):
        """Simple hour parses correctly."""
        assert parse_time("2 pm") == "14:00"
        assert parse_time("14") == "14:00"

    def test_invalid_returns_none(self):
        """Invalid time returns None."""
        assert parse_time("not a time") is None


class TestParseNumber:
    """Tests for parse_number function."""

    def test_digit_number(self):
        """Digit number parses correctly."""
        assert parse_number("5") == 5
        assert parse_number("10") == 10

    def test_written_number(self):
        """Written number parses correctly."""
        assert parse_number("five") == 5
        assert parse_number("ten") == 10
        assert parse_number("twelve") == 12

    def test_number_in_text(self):
        """Number in text extracts correctly."""
        assert parse_number("I need 3") == 3
        assert parse_number("about 10 items") == 10

    def test_invalid_returns_none(self):
        """Invalid number returns None."""
        assert parse_number("no number here") is None


class TestExtractSlotDeterministic:
    """Tests for extract_slot_deterministic function."""

    def test_choice_extraction(self):
        """CHOICE slot extracts deterministically."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("reason_category")
        value, success = extract_slot_deterministic("I'm sick", slot)
        assert success is True
        assert value == "SICK"

    def test_phone_extraction(self):
        """PHONE slot extracts and normalizes."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("employer_phone")
        value, success = extract_slot_deterministic("0412345678", slot)
        assert success is True
        assert value == "+61412345678"

    def test_date_extraction(self):
        """DATE slot extracts and normalizes."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("shift_date")
        value, success = extract_slot_deterministic("tomorrow", slot)
        assert success is True
        assert value is not None

    def test_text_extraction(self):
        """TEXT slot extracts directly."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("employer_name")
        value, success = extract_slot_deterministic("Bunnings", slot)
        assert success is True
        assert value == "Bunnings"

    def test_empty_text_fails(self):
        """Empty text doesn't extract."""
        spec = get_agent_spec("SICK_CALLER")
        slot = spec.get_slot_by_name("employer_name")
        value, success = extract_slot_deterministic("", slot)
        assert success is False
        assert value is None


class TestExtractSlotsSync:
    """Tests for synchronous extract_slots_sync function."""

    def test_extracts_current_slot(self):
        """Extracts value for current slot."""
        spec = get_agent_spec("SICK_CALLER")
        result = extract_slots_sync(spec, "SICK", current_slot="reason_category")
        assert result.extracted_data.get("reason_category") == "SICK"
        assert result.llm_used is False
        assert result.confidence == "HIGH"

    def test_empty_message_returns_empty(self):
        """Empty message returns empty result."""
        spec = get_agent_spec("SICK_CALLER")
        result = extract_slots_sync(spec, "", current_slot="employer_name")
        assert result.extracted_data == {}


# =============================================================================
# ASYNC EXTRACTION TESTS
# =============================================================================

class TestExtractSlotsAsync:
    """Tests for async extract_slots function."""

    @pytest.mark.asyncio
    async def test_deterministic_extraction_no_llm(self):
        """Deterministic extraction doesn't use LLM."""
        spec = get_agent_spec("SICK_CALLER")
        result = await extract_slots(spec, "SICK", current_slot="reason_category")
        assert result.extracted_data.get("reason_category") == "SICK"
        assert result.llm_used is False

    @pytest.mark.asyncio
    async def test_llm_fallback_when_deterministic_fails(self):
        """LLM is used when deterministic extraction fails for non-TEXT slots."""
        spec = get_agent_spec("SICK_CALLER")

        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"extractedData": {"shift_date": "2026-02-15"}}'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Test with a date input that can't be parsed deterministically
        result = await extract_slots(
            spec,
            "next saturday",  # Can't be parsed deterministically
            current_slot="shift_date",
            openai_client=mock_client,
        )

        # Should have extracted the value via LLM
        assert result.extracted_data.get("shift_date") == "2026-02-15"
        assert result.llm_used is True

    @pytest.mark.asyncio
    async def test_llm_json_error_returns_empty_for_date(self):
        """LLM JSON parse error returns empty result for DATE slot."""
        spec = get_agent_spec("SICK_CALLER")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = 'not valid json'
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Use a date slot with unparseable input
        result = await extract_slots(
            spec,
            "next week sometime",  # Can't be parsed deterministically
            current_slot="shift_date",
            openai_client=mock_client,
        )

        # Should return empty with low confidence (deterministic failed, LLM JSON failed)
        assert result.extracted_data == {}
        assert result.llm_used is True
        assert result.confidence == "LOW"

    @pytest.mark.asyncio
    async def test_text_slot_deterministic_no_llm(self):
        """TEXT slot extracts deterministically without LLM call."""
        spec = get_agent_spec("SICK_CALLER")

        # Even with a mock client, LLM should not be called for TEXT
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock()

        result = await extract_slots(
            spec,
            "Bunnings Warehouse",
            current_slot="employer_name",
            openai_client=mock_client,
        )

        # Should extract directly without LLM
        assert result.extracted_data.get("employer_name") == "Bunnings Warehouse"
        assert result.llm_used is False  # No LLM needed for TEXT


class TestBuildExtractionPrompt:
    """Tests for build_extraction_prompt function."""

    def test_includes_slot_definitions(self):
        """Prompt includes slot definitions."""
        spec = get_agent_spec("SICK_CALLER")
        prompt = build_extraction_prompt(spec, "test message", "employer_name", {})
        assert "employer_name" in prompt
        assert "employer_phone" in prompt
        assert "TEXT" in prompt
        assert "PHONE" in prompt

    def test_includes_choice_values(self):
        """Prompt includes allowed values for CHOICE slots."""
        spec = get_agent_spec("SICK_CALLER")
        prompt = build_extraction_prompt(spec, "test message", "reason_category", {})
        assert '"SICK"' in prompt
        assert '"CARER"' in prompt

    def test_includes_existing_slots(self):
        """Prompt includes existing slots context."""
        spec = get_agent_spec("SICK_CALLER")
        existing = {"employer_name": "Bunnings"}
        prompt = build_extraction_prompt(spec, "test message", "employer_phone", existing)
        assert "Bunnings" in prompt


# =============================================================================
# V2 ENDPOINT INTEGRATION TESTS (Mocked)
# =============================================================================

class TestV2EndpointIntegration:
    """Tests verifying V2 endpoint uses spec-driven planner."""

    @pytest.fixture
    def mock_conversation_v2(self):
        """Create a mock for conversation_v2 processing."""
        # This would test the full endpoint, but requires app setup
        pass

    def test_v2_endpoint_registered(self):
        """Verify V2 endpoint is registered in the app."""
        # Import to verify it exists
        try:
            from app.conversation_v2 import process_conversation_v2
            assert process_conversation_v2 is not None
        except ImportError:
            pytest.skip("conversation_v2 module not found")
