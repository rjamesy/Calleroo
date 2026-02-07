"""
Deterministic conversation planner.

This module is the SINGLE SOURCE OF TRUTH for conversation flow decisions.
It uses AgentSpec to determine:
- Which slot to ask for next
- When to show confirmation
- When the conversation is complete
- When to trigger place search

NO LLM calls are made in this module. All logic is deterministic.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List
import logging
import re

from agents.specs import AgentSpec, SlotSpec, InputType, PhoneSource

logger = logging.getLogger(__name__)


class NextAction(str, Enum):
    """Possible next actions in the conversation flow."""
    ASK_QUESTION = "ASK_QUESTION"
    CONFIRM = "CONFIRM"
    COMPLETE = "COMPLETE"
    FIND_PLACE = "FIND_PLACE"


class ClientAction(str, Enum):
    """Actions the client can send to influence flow."""
    CONFIRM = "CONFIRM"
    REJECT = "REJECT"


@dataclass
class QuickReply:
    """A quick reply option for the UI."""
    label: str
    value: str


@dataclass
class Question:
    """A question to ask the user."""
    slot_name: str
    input_type: str
    prompt: str
    quick_replies: Optional[List[QuickReply]] = None


@dataclass
class ConfirmationCard:
    """A confirmation card to show the user."""
    title: str
    lines: List[str]
    confirm_label: str = "Yes, that's correct"
    reject_label: str = "No, let me change something"
    card_id: Optional[str] = None


@dataclass
class PlaceSearchParams:
    """Parameters for triggering a place search."""
    query: str
    area: str


@dataclass
class PlannerResult:
    """Result of the planner decision."""
    next_action: NextAction
    question: Optional[Question] = None
    confirmation_card: Optional[ConfirmationCard] = None
    place_search_params: Optional[PlaceSearchParams] = None
    assistant_message: str = ""


# =============================================================================
# SLOT VALUE CHECKING
# =============================================================================

def is_slot_filled(slots: Dict[str, Any], slot_name: str) -> bool:
    """
    Check if a slot has a valid (non-empty) value.

    A slot is considered filled if:
    - It exists in the slots dict
    - Its value is not None
    - Its value is not an empty string
    - Its value is not 0 (for number slots, 0 might be valid, but we treat it as unfilled)
    """
    value = slots.get(slot_name)
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    # Note: 0 is treated as filled for numbers (quantity=0 is valid)
    return True


# =============================================================================
# PLACE RESOLUTION CHECKING
# =============================================================================

# Canonical slot names for resolved place data
# These are written by the Android app after PlaceSearch/PlaceDetails flow
PLACE_ID_SLOT = "place_id"
PLACE_PHONE_SLOT = "place_phone"  # E.164 format

# Internal flag to track if user has confirmed core details (before place selection)
# This prevents showing a second confirmation card after place selection
CONFIRMED_DETAILS_FLAG = "_confirmed_core_details"


def is_place_resolved(slots: Dict[str, Any]) -> bool:
    """
    Check if a place has been resolved (selected from search).

    A place is considered resolved when we have both:
    - place_id: The Google Places ID
    - place_phone: The phone number in E.164 format

    This is required for phoneSource=PLACE agents before COMPLETE.

    Args:
        slots: Current slot values

    Returns:
        True if place is resolved with both ID and phone
    """
    place_id = slots.get(PLACE_ID_SLOT)
    place_phone = slots.get(PLACE_PHONE_SLOT)

    has_place_id = place_id is not None and str(place_id).strip() != ""
    has_place_phone = place_phone is not None and str(place_phone).strip() != ""

    return has_place_id and has_place_phone


def has_confirmed_details(slots: Dict[str, Any]) -> bool:
    """
    Check if user has already confirmed core details.

    This flag is set when user confirms the details, before place search.
    It prevents showing a second confirmation card after place selection.

    Args:
        slots: Current slot values

    Returns:
        True if core details have been confirmed
    """
    flag = slots.get(CONFIRMED_DETAILS_FLAG)
    return flag is True or flag == "true" or flag == True


def _is_required_now(slot_spec: SlotSpec, slots: Dict[str, Any]) -> bool:
    """
    Check if a slot is required at this moment.

    A slot is required if:
    - slot_spec.required == True (always required)
    - OR slot_spec.required_if(slots) == True (conditionally required)

    Args:
        slot_spec: The slot specification
        slots: Current slot values

    Returns:
        True if the slot is required now
    """
    return slot_spec.required or (slot_spec.required_if is not None and slot_spec.required_if(slots))


def get_next_slot(spec: AgentSpec, slots: Dict[str, Any]) -> Optional[SlotSpec]:
    """
    Get the next slot that needs to be filled.

    Processing order:
    1. Required slots (static or conditional) that are not filled (in order)
    2. Optional slots with ask_if predicate that returns True and not filled

    Args:
        spec: The agent specification
        slots: Current slot values

    Returns:
        The next SlotSpec to ask for, or None if all applicable slots are filled
    """
    for slot_spec in spec.slots_in_order:
        # Skip already filled slots
        if is_slot_filled(slots, slot_spec.name):
            continue

        # Check if required now (static or conditional)
        if _is_required_now(slot_spec, slots):
            return slot_spec

        # Optional slots with ask_if: check predicate
        if slot_spec.ask_if is not None and slot_spec.should_ask(slots):
            return slot_spec

    return None


def get_missing_required_slots(spec: AgentSpec, slots: Dict[str, Any]) -> List[str]:
    """
    Get list of required slot names that are missing.

    Includes both statically required and conditionally required slots.

    Args:
        spec: The agent specification
        slots: Current slot values

    Returns:
        List of missing required slot names
    """
    missing = []
    for slot_spec in spec.slots_in_order:
        if _is_required_now(slot_spec, slots) and not is_slot_filled(slots, slot_spec.name):
            missing.append(slot_spec.name)
    return missing


# =============================================================================
# FIND_PLACE DETECTION
# =============================================================================

# Keywords that indicate user doesn't know the phone number
FIND_PLACE_KEYWORDS = [
    "don't know",
    "dont know",
    "not sure",
    "find it",
    "look it up",
    "search for it",
    "i don't have",
    "i dont have",
    "can you find",
    "help me find",
    "find the number",
    "look up the number",
    "search",
    "find",
]


def should_trigger_find_place(
    user_message: str,
    current_slot: Optional[SlotSpec],
) -> bool:
    """
    Check if the user message indicates they want to search for a phone number.

    This is only relevant when:
    - We're asking for a PHONE slot
    - User indicates they don't know the number

    Args:
        user_message: The user's message
        current_slot: The slot we're currently asking for

    Returns:
        True if we should trigger FIND_PLACE action
    """
    if current_slot is None:
        return False

    if current_slot.input_type != InputType.PHONE:
        return False

    message_lower = user_message.lower()
    for keyword in FIND_PLACE_KEYWORDS:
        if keyword in message_lower:
            return True

    return False


# =============================================================================
# QUESTION BUILDING
# =============================================================================

def build_question(slot_spec: SlotSpec) -> Question:
    """
    Build a Question object from a SlotSpec.

    Args:
        slot_spec: The slot specification

    Returns:
        A Question object ready for the response
    """
    quick_replies = None
    qr_data = slot_spec.get_quick_replies()
    if qr_data:
        quick_replies = [QuickReply(label=qr["label"], value=qr["value"]) for qr in qr_data]

    return Question(
        slot_name=slot_spec.name,
        input_type=slot_spec.input_type.value,
        prompt=slot_spec.prompt,
        quick_replies=quick_replies,
    )


# =============================================================================
# CONFIRMATION CARD BUILDING
# =============================================================================

def format_slot_value_for_display(slot_name: str, value: Any) -> str:
    """
    Format a slot value for display in confirmation card.

    Args:
        slot_name: The slot name
        value: The slot value

    Returns:
        Formatted string for display
    """
    if value is None:
        return "(not provided)"

    value_str = str(value)

    # Map reason codes to human-readable labels
    reason_mapping = {
        "SICK": "I'm sick",
        "CARER": "Caring for someone",
        "MENTAL_HEALTH": "Mental health day",
        "MEDICAL_APPOINTMENT": "Medical appointment",
    }

    if slot_name == "reason_category" and value_str in reason_mapping:
        return reason_mapping[value_str]

    return value_str


def build_confirmation_card(spec: AgentSpec, slots: Dict[str, Any]) -> ConfirmationCard:
    """
    Build a confirmation card from the AgentSpec template and current slots.

    Lines with empty or "(not provided)" values are omitted for cleaner display.

    Args:
        spec: The agent specification
        slots: Current slot values

    Returns:
        A ConfirmationCard object ready for the response
    """
    # Format each line by substituting slot values
    formatted_lines = []
    for line_template in spec.confirm_lines:
        formatted_line = line_template
        # Find all {slot_name} placeholders and replace them
        placeholders = re.findall(r'\{(\w+)\}', line_template)
        skip_line = False
        for placeholder in placeholders:
            value = slots.get(placeholder)
            display_value = format_slot_value_for_display(placeholder, value)

            # Check if value is empty/not provided/not sure
            if value is None or str(value).strip() == "" or str(value).strip().lower() in ("not sure", "not_sure", "unsure"):
                skip_line = True
                break

            formatted_line = formatted_line.replace(f"{{{placeholder}}}", display_value)

        # Only add line if it has meaningful content
        if not skip_line:
            formatted_lines.append(formatted_line)

    # Generate stable card ID from content hash
    card_content = f"{spec.confirm_title}|{'|'.join(formatted_lines)}"
    card_id = hex(hash(card_content) & 0xFFFFFFFF)[2:]

    return ConfirmationCard(
        title=spec.confirm_title,
        lines=formatted_lines,
        confirm_label="Yes, that's correct",
        reject_label="No, let me change something",
        card_id=card_id,
    )


# =============================================================================
# PLACE SEARCH PARAMS BUILDING
# =============================================================================

def build_place_search_params(spec: AgentSpec, slots: Dict[str, Any]) -> PlaceSearchParams:
    """
    Build place search parameters from the AgentSpec and current slots.

    GUARANTEE: Always returns non-empty query and area.
    - Query priority: place_query_slot value -> "store" (fallback)
    - Area priority: place_area_slot value -> "Australia" (fallback)

    Args:
        spec: The agent specification
        slots: Current slot values

    Returns:
        PlaceSearchParams object with non-empty query and area
    """
    query = ""
    area = ""

    # Try to get query from spec's place_query_slot
    if spec.place_query_slot:
        slot_value = slots.get(spec.place_query_slot)
        if slot_value is not None:
            query = str(slot_value).strip()

    # Try to get area from spec's place_area_slot
    if spec.place_area_slot:
        slot_value = slots.get(spec.place_area_slot)
        if slot_value is not None:
            area = str(slot_value).strip()

    # Fallback: ensure query is never empty
    if not query:
        # Try common slot names as fallback
        for fallback_slot in ["retailer_name", "restaurant_name", "business_name"]:
            slot_value = slots.get(fallback_slot)
            if slot_value:
                query = str(slot_value).strip()
                break

    # Final fallback for query
    if not query:
        query = "store"
        logger.warning(f"build_place_search_params: No query slot found, using fallback 'store'")

    # Fallback: ensure area is never empty
    if not area:
        # Try common area slot names as fallback
        for fallback_slot in ["store_location", "suburb_or_area", "business_location", "location"]:
            slot_value = slots.get(fallback_slot)
            if slot_value:
                area = str(slot_value).strip()
                break

    # Final fallback for area
    if not area:
        area = "Australia"

    return PlaceSearchParams(query=query, area=area)


# =============================================================================
# MAIN PLANNER
# =============================================================================

def decide_next_action(
    spec: AgentSpec,
    slots: Dict[str, Any],
    client_action: Optional[str] = None,
    user_message: str = "",
    current_question_slot: Optional[str] = None,
) -> PlannerResult:
    """
    Decide the next action in the conversation flow.

    This is the main entry point for the deterministic planner.
    It returns a PlannerResult with the next action and any associated data.

    Flow for phoneSource=PLACE agents (STOCK_CHECKER, RESTAURANT_RESERVATION, etc.):
    1. Collect all required slots → ASK_QUESTION for each
    2. All slots filled → CONFIRM (show confirmation card)
    3. User taps CONFIRM → set _confirmed_core_details flag
       - If place not resolved → FIND_PLACE (trigger place search)
       - If place resolved → COMPLETE
    4. After place selected (place_id + place_phone in slots) → COMPLETE directly
       (no second confirmation card)

    Flow for phoneSource=DIRECT_SLOT agents (SICK_CALLER):
    1. Collect all required slots → ASK_QUESTION for each
    2. All slots filled → CONFIRM
    3. User taps CONFIRM → COMPLETE

    Other rules:
    - If client_action == REJECT → ASK_QUESTION (let user edit)
    - If asking for PHONE and user says "don't know" → FIND_PLACE

    Args:
        spec: The agent specification
        slots: Current slot values (already merged)
        client_action: Optional client action (CONFIRM or REJECT)
        user_message: The user's message (for FIND_PLACE detection)
        current_question_slot: The slot we're currently asking for (for FIND_PLACE detection)

    Returns:
        PlannerResult with the decision and associated data
    """
    # Rule 1: CONFIRM action handling
    if client_action == ClientAction.CONFIRM.value or client_action == "CONFIRM":
        # For PLACE agents, check if place is resolved
        if spec.phone_source == PhoneSource.PLACE and not is_place_resolved(slots):
            # User confirmed details but place not selected yet
            # Set the confirmed flag and trigger place search
            logger.info(f"Planner: client_action=CONFIRM, place not resolved => FIND_PLACE")
            place_params = build_place_search_params(spec, slots)
            return PlannerResult(
                next_action=NextAction.FIND_PLACE,
                place_search_params=place_params,
                assistant_message="Great! Now let's find the store to call.",
                # Note: The flag will be set in extractedData by conversation_v2
            )

        # Place resolved or not a PLACE agent => COMPLETE
        logger.info(f"Planner: client_action=CONFIRM => COMPLETE")
        return PlannerResult(
            next_action=NextAction.COMPLETE,
            assistant_message="Great! I'll place the call now.",
        )

    # Rule 2: REJECT action => ASK_QUESTION
    if client_action == ClientAction.REJECT.value or client_action == "REJECT":
        logger.info(f"Planner: client_action=REJECT => ASK_QUESTION")
        # Ask what they want to change, or restart from first missing slot
        next_slot = get_next_slot(spec, slots)
        if next_slot:
            question = build_question(next_slot)
            return PlannerResult(
                next_action=NextAction.ASK_QUESTION,
                question=question,
                assistant_message=f"No problem! {next_slot.prompt}",
            )
        else:
            # All slots filled but user rejected - let them specify
            return PlannerResult(
                next_action=NextAction.ASK_QUESTION,
                assistant_message="What would you like to change?",
            )

    # Get current slot spec if we have the name
    current_slot_spec = None
    if current_question_slot:
        current_slot_spec = spec.get_slot_by_name(current_question_slot)

    # Rule 3: Check for FIND_PLACE trigger (only for PHONE slots when user says "don't know")
    if should_trigger_find_place(user_message, current_slot_spec):
        logger.info(f"Planner: FIND_PLACE triggered by user message")
        place_params = build_place_search_params(spec, slots)
        return PlannerResult(
            next_action=NextAction.FIND_PLACE,
            place_search_params=place_params,
            assistant_message="I'll help you find the number.",
        )

    # Rule 4 & 5: Check if all required slots are filled
    next_slot = get_next_slot(spec, slots)

    if next_slot is None:
        # All required slots filled
        # For PLACE agents: check if user already confirmed and place is now resolved
        if spec.phone_source == PhoneSource.PLACE:
            if has_confirmed_details(slots) and is_place_resolved(slots):
                # User already confirmed, place is now selected => go directly to COMPLETE
                logger.info(f"Planner: All slots filled, details confirmed, place resolved => COMPLETE")
                return PlannerResult(
                    next_action=NextAction.COMPLETE,
                    assistant_message="Great! I'll place the call now.",
                )
            elif has_confirmed_details(slots) and not is_place_resolved(slots):
                # User confirmed but place not resolved (shouldn't happen normally, but handle it)
                logger.info(f"Planner: Details confirmed but place not resolved => FIND_PLACE")
                place_params = build_place_search_params(spec, slots)
                return PlannerResult(
                    next_action=NextAction.FIND_PLACE,
                    place_search_params=place_params,
                    assistant_message="Now let's find the store to call.",
                )

        # Normal case: show confirmation card
        # (For PLACE agents without confirmed flag, or for DIRECT_SLOT agents)
        logger.info(f"Planner: All required slots filled => CONFIRM")
        confirmation_card = build_confirmation_card(spec, slots)
        return PlannerResult(
            next_action=NextAction.CONFIRM,
            confirmation_card=confirmation_card,
            assistant_message="Let me confirm the details:",
        )
    else:
        # Still have slots to fill => ASK_QUESTION
        logger.info(f"Planner: Next slot to ask: {next_slot.name}")
        question = build_question(next_slot)
        return PlannerResult(
            next_action=NextAction.ASK_QUESTION,
            question=question,
            assistant_message=next_slot.prompt,
        )
