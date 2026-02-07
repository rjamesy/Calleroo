"""
AgentSpec and SlotSpec definitions.

This module defines the declarative specification for each agent type.
The planner and extractor use these specs to drive conversation flow
deterministically, without per-agent branching logic.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Callable


class InputType(str, Enum):
    """Input types for slots."""
    TEXT = "TEXT"
    PHONE = "PHONE"
    DATE = "DATE"
    TIME = "TIME"
    NUMBER = "NUMBER"
    CHOICE = "CHOICE"
    YES_NO = "YES_NO"


class PhoneFlowMode(str, Enum):
    """How the live phone call is conducted."""
    DETERMINISTIC_SCRIPT = "DETERMINISTIC_SCRIPT"  # Fixed TwiML, no OpenAI
    LLM_DIALOG = "LLM_DIALOG"  # OpenAI-driven conversation


class PhoneSource(str, Enum):
    """Where the phone number comes from."""
    PLACE = "PLACE"  # From place search (Google Places)
    DIRECT_SLOT = "DIRECT_SLOT"  # From a slot collected during conversation


@dataclass
class Choice:
    """A choice option for CHOICE or YES_NO input types."""
    label: str
    value: str


@dataclass
class SlotSpec:
    """
    Specification for a single slot to collect.

    Attributes:
        name: The slot key (e.g., "employer_name", "shift_date")
        required: Whether this slot must be filled before confirmation
        input_type: The type of input expected
        prompt: The question to ask the user for this slot
        choices: For CHOICE type, the available options
        validators: Optional list of validator function names
        normalizers: Optional list of normalizer function names
        description: Human-readable description for debugging
        ask_if: Optional predicate function that takes slots dict and returns bool.
                If provided, this slot is only asked when ask_if(slots) returns True.
                Used for conditional/contextual slots.
        required_if: Optional predicate function that makes this slot conditionally required.
                     If required_if(slots) returns True, this slot is treated as required.
    """
    name: str
    required: bool
    input_type: InputType
    prompt: str
    choices: Optional[List[Choice]] = None
    validators: Optional[List[str]] = None
    normalizers: Optional[List[str]] = None
    description: Optional[str] = None
    ask_if: Optional[Callable[[Dict[str, Any]], bool]] = None
    required_if: Optional[Callable[[Dict[str, Any]], bool]] = None

    def get_quick_replies(self) -> Optional[List[Dict[str, str]]]:
        """
        Get quick replies for this slot based on input type.
        Returns list of {label, value} dicts for UI chips.
        """
        if self.input_type == InputType.CHOICE and self.choices:
            return [{"label": c.label, "value": c.value} for c in self.choices]
        elif self.input_type == InputType.YES_NO:
            return [
                {"label": "Yes", "value": "YES"},
                {"label": "No", "value": "NO"},
            ]
        return None

    def should_ask(self, slots: Dict[str, Any]) -> bool:
        """
        Determine if this slot should be asked.

        Required if:
        - required == True
        - OR required_if(slots) == True

        Optional if:
        - ask_if(slots) == True

        Args:
            slots: Current slot values

        Returns:
            True if this slot should be asked
        """
        # Check if conditionally required now
        is_required_now = self.required or (self.required_if is not None and self.required_if(slots))
        if is_required_now:
            return True

        # Check optional ask_if predicate
        if self.ask_if is not None:
            return self.ask_if(slots)

        return False


@dataclass
class PhoneFlow:
    """Configuration for the live phone call."""
    mode: PhoneFlowMode
    greeting_template: Optional[str] = None  # For DETERMINISTIC_SCRIPT
    message_template: Optional[str] = None  # For DETERMINISTIC_SCRIPT
    system_prompt_template: Optional[str] = None  # For LLM_DIALOG


@dataclass
class AgentSpec:
    """
    Complete specification for an agent type.

    This drives all conversation flow, call brief generation, and phone calls
    without any per-agent if/else branching.
    """
    agent_type: str
    title: str
    description: str

    # Slots in collection order (required slots first, then optional)
    slots_in_order: List[SlotSpec]

    # Confirmation card template
    confirm_title: str
    confirm_lines: List[str]  # Template strings with {slot_name} placeholders

    # Phone number source
    phone_source: PhoneSource
    direct_phone_slot: Optional[str] = None  # Required if phone_source == DIRECT_SLOT

    # Phone call configuration
    phone_flow: PhoneFlow = field(default_factory=lambda: PhoneFlow(mode=PhoneFlowMode.LLM_DIALOG))

    # Call brief templates
    objective_template: Optional[str] = None
    script_template: Optional[str] = None

    # Place search configuration (for PLACE phone source)
    place_query_slot: Optional[str] = None  # Slot to use for place search query
    place_area_slot: Optional[str] = None  # Slot to use for place search area

    def get_required_slots(self) -> List[SlotSpec]:
        """Get all required slots in order."""
        return [s for s in self.slots_in_order if s.required]

    def get_optional_slots(self) -> List[SlotSpec]:
        """Get all optional slots in order."""
        return [s for s in self.slots_in_order if not s.required]

    def get_slot_by_name(self, name: str) -> Optional[SlotSpec]:
        """Get a slot spec by name."""
        for slot in self.slots_in_order:
            if slot.name == name:
                return slot
        return None

    def get_slot_names(self) -> List[str]:
        """Get all slot names in order."""
        return [s.name for s in self.slots_in_order]

    def get_required_slot_names(self) -> List[str]:
        """Get required slot names in order."""
        return [s.name for s in self.slots_in_order if s.required]


# =============================================================================
# CONDITIONAL SLOT PREDICATES
# =============================================================================

# Category-only terms that are too generic for stock checks
GENERIC_PRODUCT_TERMS = {
    "fishing rod", "rod", "rods", "fishing reel", "reel", "reels",
    "shoes", "shoe", "sneakers", "boots", "sandals",
    "laptop", "laptops", "computer", "computers", "pc",
    "phone", "phones", "mobile", "mobiles", "smartphone",
    "tv", "television", "televisions", "monitor", "monitors",
    "headphones", "earbuds", "earphones", "speaker", "speakers",
    "camera", "cameras", "lens", "lenses",
    "printer", "printers", "keyboard", "keyboards", "mouse",
    "towel", "towels", "sheets", "sheet", "pillow", "pillows",
    "chair", "chairs", "table", "tables", "desk", "desks",
    "lamp", "lamps", "light", "lights", "bulb", "bulbs",
    "tool", "tools", "drill", "drills", "saw", "saws",
    "paint", "paints", "brush", "brushes",
    "garden hose", "hose", "hoses", "shovel", "rake",
    "bike", "bikes", "bicycle", "bicycles",
    "tent", "tents", "camping gear", "sleeping bag",
    "jacket", "jackets", "coat", "coats", "shirt", "shirts",
    "pants", "jeans", "shorts", "dress", "dresses",
}


def is_generic_product_name(product_name: Optional[str]) -> bool:
    """
    Check if a product name is too generic and needs more details.

    A product name is considered generic if:
    - It's None or empty
    - It has 2 or fewer words
    - It matches a known generic category term

    Args:
        product_name: The product name to check

    Returns:
        True if the product name is generic and needs more details
    """
    if not product_name:
        return True

    name_lower = product_name.strip().lower()
    if not name_lower:
        return True

    # Check against known generic terms
    if name_lower in GENERIC_PRODUCT_TERMS:
        return True

    # Check word count - 2 or fewer words is likely generic
    words = name_lower.split()
    if len(words) <= 2:
        return True

    return False


def is_generic_product(slots: Dict[str, Any]) -> bool:
    """
    Check if the current product_name in slots is generic.

    A product is generic if:
    - It's in GENERIC_PRODUCT_TERMS, OR
    - It has 2 or fewer words

    Args:
        slots: Current slot values

    Returns:
        True if product is generic
    """
    name = (slots.get("product_name") or "").strip().lower()
    if not name:
        return False
    # Check if it's a known generic term
    if name in GENERIC_PRODUCT_TERMS:
        return True
    # Short names (2 words or less) are considered generic
    if len(name.split()) <= 2:
        return True
    return False


def needs_product_details(slots: Dict[str, Any]) -> bool:
    """
    Check if product_details is required (conditionally).

    Required when:
    - Product is generic
    - User hasn't said broad_ok=YES
    - Details are empty or "not sure"

    Args:
        slots: Current slot values

    Returns:
        True if product_details should be required
    """
    if not is_generic_product(slots):
        return False
    broad_ok = (slots.get("broad_ok") or "").strip().upper()
    if broad_ok == "YES":
        return False
    details = (slots.get("product_details") or "").strip().lower()
    if details in ("", "not sure", "not_sure", "unsure", "skip"):
        return True
    return False


def needs_broad_ok(slots: Dict[str, Any]) -> bool:
    """
    Check if broad_ok confirmation is required.

    Required when:
    - Product is generic
    - User said "not sure" for product_details
    - broad_ok hasn't been answered yet

    Args:
        slots: Current slot values

    Returns:
        True if broad_ok should be required
    """
    if not is_generic_product(slots):
        return False
    details = (slots.get("product_details") or "").strip().lower()
    if details in ("not sure", "not_sure", "unsure", "skip", ""):
        # Only ask if not already answered
        broad_ok_val = slots.get("broad_ok")
        return broad_ok_val is None or str(broad_ok_val).strip() == ""
    return False


def should_ask_product_details(slots: Dict[str, Any]) -> bool:
    """
    Predicate for product_details slot (ask_if).

    Only ask for product details if the product_name is generic.

    Args:
        slots: Current slot values

    Returns:
        True if we should ask for product details
    """
    product_name = slots.get("product_name")
    return is_generic_product_name(product_name)


# =============================================================================
# AGENT REGISTRY
# =============================================================================

SICK_CALLER_SPEC = AgentSpec(
    agent_type="SICK_CALLER",
    title="Call in Sick",
    description="Notify your workplace that you are unwell",

    slots_in_order=[
        SlotSpec(
            name="employer_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="Who should I call to notify? (e.g., your manager's name or company name)",
            description="Name of employer/manager to call"
        ),
        SlotSpec(
            name="employer_phone",
            required=True,
            input_type=InputType.PHONE,
            prompt="What's their phone number?",
            description="Phone number to call"
        ),
        SlotSpec(
            name="caller_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="What name should I give them? (your name)",
            description="User's name to provide"
        ),
        SlotSpec(
            name="shift_date",
            required=True,
            input_type=InputType.DATE,
            prompt="When is your shift?",
            description="Date of the shift being missed"
        ),
        SlotSpec(
            name="shift_start_time",
            required=True,
            input_type=InputType.TIME,
            prompt="What time does your shift start?",
            description="Start time of the shift"
        ),
        SlotSpec(
            name="reason_category",
            required=True,
            input_type=InputType.CHOICE,
            prompt="What's the reason for calling in?",
            choices=[
                Choice(label="I'm sick", value="SICK"),
                Choice(label="Caring for someone", value="CARER"),
                Choice(label="Mental health day", value="MENTAL_HEALTH"),
                Choice(label="Medical appointment", value="MEDICAL_APPOINTMENT"),
            ],
            description="Reason category for absence"
        ),
        SlotSpec(
            name="expected_return_date",
            required=False,
            input_type=InputType.DATE,
            prompt="When do you expect to return? (optional)",
            description="Expected return date"
        ),
        SlotSpec(
            name="note_for_team",
            required=False,
            input_type=InputType.TEXT,
            prompt="Any message for your team? (optional)",
            description="Additional note"
        ),
    ],

    confirm_title="Call In Sick",
    confirm_lines=[
        "Calling: {employer_name}",
        "Phone: {employer_phone}",
        "Your name: {caller_name}",
        "Shift: {shift_date} at {shift_start_time}",
        # IMPORTANT: render the LABEL (e.g. "I'm sick") in your UI/template, not the raw enum value
        "Reason: {reason_category}",
        "Return: {expected_return_date}",  # show only if present in UI
        "Note: {note_for_team}",           # show only if present in UI
    ],

    phone_source=PhoneSource.DIRECT_SLOT,
    direct_phone_slot="employer_phone",

    phone_flow=PhoneFlow(
        mode=PhoneFlowMode.DETERMINISTIC_SCRIPT,

        # Keep greeting short and natural
        greeting_template="Hi—I'm Calleroo, the mobile app, calling on behalf of {caller_name}.",

        # IMPORTANT IMPLEMENTATION NOTES:
        # - Use the reason_category *LABEL* (or a mapped spoken phrase) when filling {reason_spoken}
        # - expected_return_sentence/note_sentence should resolve to "" if not provided
        # - Do NOT ask "Did you receive this message?" (sounds robotic)
        message_template=(
            "{caller_name} won’t be able to make their shift on {shift_date} at {shift_start_time}. "
            "{reason_spoken} "
            "{expected_return_sentence}"
            "{note_sentence}"
            "Thanks for your help."
        ),
    ),

    objective_template="Notify {employer_name} that {caller_name} cannot attend their shift on {shift_date}",
    script_template=(
        "Call {employer_name} at {employer_phone} to notify them that {caller_name} "
        "cannot attend their shift on {shift_date} at {shift_start_time}. "
        "Reason: {reason_category}."
    ),
)


STOCK_CHECKER_SPEC = AgentSpec(
    agent_type="STOCK_CHECKER",
    title="Stock Check",
    description="Check product availability at retailers",

    slots_in_order=[
        SlotSpec(
            name="retailer_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="Which retailer should I call?",
            description="Name of the retailer"
        ),
        SlotSpec(
            name="product_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="What product are you looking for?",
            description="Product to check availability"
        ),
        SlotSpec(
            name="product_details",
            required=False,
            required_if=needs_product_details,  # Conditionally required for generic products
            input_type=InputType.TEXT,
            prompt="Do you know the brand/model or key specs (size/voltage/type)? If not, say 'not sure'.",
            description="Brand/model/details for generic products",
        ),
        SlotSpec(
            name="broad_ok",
            required=False,
            required_if=needs_broad_ok,  # Required when product is generic and details are "not sure"
            input_type=InputType.YES_NO,
            prompt="This is pretty broad, so the store may ask for more detail. Do you still want me to call and ask generally?",
            description="User approval to proceed with generic product",
        ),
        SlotSpec(
            name="quantity",
            required=True,
            input_type=InputType.NUMBER,
            prompt="How many do you need?",
            description="Quantity needed"
        ),
        SlotSpec(
            name="store_location",
            required=True,
            input_type=InputType.TEXT,
            prompt="Which suburb or area should I search in?",
            description="Location for store search"
        ),
        SlotSpec(
            name="brand",
            required=False,
            input_type=InputType.TEXT,
            prompt="Any specific brand? (optional)",
            description="Brand preference"
        ),
        SlotSpec(
            name="model",
            required=False,
            input_type=InputType.TEXT,
            prompt="Any specific model? (optional)",
            description="Model number or name"
        ),
        SlotSpec(
            name="variant",
            required=False,
            input_type=InputType.TEXT,
            prompt="Any specific variant (size, color)? (optional)",
            description="Variant details"
        ),
    ],

    confirm_title="Check Stock",
    confirm_lines=[
        "Retailer: {retailer_name}",
        "Product: {product_name}",
        "Details: {product_details}",
        "Quantity: {quantity}",
        "Location: {store_location}",
    ],

    phone_source=PhoneSource.PLACE,
    place_query_slot="retailer_name",
    place_area_slot="store_location",

    phone_flow=PhoneFlow(
        mode=PhoneFlowMode.LLM_DIALOG,
        greeting_template="Hi—I'm Calleroo, the mobile app, calling on behalf of a customer.",
        system_prompt_template=(
            "You are calling {retailer_name} to check stock for a customer.\n"
            "Item: {product_name}.\n"
            "Details (if provided): {product_details}.\n"
            "Quantity needed: {quantity}.\n\n"
            "Be polite and practical. Identify yourself as Calleroo (an AI assistant from a mobile app) calling on behalf of the customer.\n"
            "Say the full item name once, then refer to it as 'the item' or 'this item' (do not keep repeating the full name).\n"
            "Ask if it's in stock. If not, ask ETA (only if enabled) or nearest store (only if enabled).\n"
        ),
    ),

    objective_template="Check if {retailer_name} has {quantity}x {product_name} in stock",
    script_template=(
        "Call {retailer_name} to check availability of {product_name}. "
        "Customer needs {quantity} units near {store_location}."
    ),
)


RESTAURANT_RESERVATION_SPEC = AgentSpec(
    agent_type="RESTAURANT_RESERVATION",
    title="Book Restaurant",
    description="Book a table at a restaurant",

    slots_in_order=[
        SlotSpec(
            name="restaurant_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="Which restaurant would you like to book?",
            description="Name of the restaurant"
        ),
        SlotSpec(
            name="party_size",
            required=True,
            input_type=InputType.NUMBER,
            prompt="How many people?",
            description="Number of guests"
        ),
        SlotSpec(
            name="date",
            required=True,
            input_type=InputType.DATE,
            prompt="What date would you like to book for?",
            description="Reservation date"
        ),
        SlotSpec(
            name="time",
            required=True,
            input_type=InputType.TIME,
            prompt="What time would you prefer?",
            description="Reservation time"
        ),
        SlotSpec(
            name="suburb_or_area",
            required=False,
            input_type=InputType.TEXT,
            prompt="Which suburb or area? (optional if restaurant name is unique)",
            description="Location area"
        ),
        SlotSpec(
            name="share_contact",
            required=False,
            input_type=InputType.YES_NO,
            prompt="Should I share your contact details with the restaurant?",
            description="Whether to share contact info"
        ),
    ],

    confirm_title="Book Restaurant",
    confirm_lines=[
        "Restaurant: {restaurant_name}",
        "Party size: {party_size} people",
        "Date: {date}",
        "Time: {time}",
    ],

    phone_source=PhoneSource.PLACE,
    place_query_slot="restaurant_name",
    place_area_slot="suburb_or_area",

    phone_flow=PhoneFlow(
        mode=PhoneFlowMode.LLM_DIALOG,
        system_prompt_template=(
            "You are calling {restaurant_name} to make a reservation. "
            "Request a table for {party_size} people on {date} at {time}. "
            "Be polite, identify yourself as an AI assistant making a booking on behalf of a customer."
        ),
    ),

    objective_template="Book a table for {party_size} at {restaurant_name} on {date} at {time}",
    script_template=(
        "Call {restaurant_name} to book a table for {party_size} people on {date} at {time}."
    ),
)


CANCEL_APPOINTMENT_SPEC = AgentSpec(
    agent_type="CANCEL_APPOINTMENT",
    title="Cancel Appointment",
    description="Cancel an existing booking",

    slots_in_order=[
        SlotSpec(
            name="business_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="What's the name of the business where you have the appointment?",
            description="Business name"
        ),
        SlotSpec(
            name="appointment_day",
            required=True,
            input_type=InputType.DATE,
            prompt="What day is your appointment?",
            description="Appointment date"
        ),
        SlotSpec(
            name="appointment_time",
            required=True,
            input_type=InputType.TIME,
            prompt="What time is the appointment?",
            description="Appointment time"
        ),
        SlotSpec(
            name="customer_name",
            required=True,
            input_type=InputType.TEXT,
            prompt="What name is the booking under?",
            description="Name on the booking"
        ),
        SlotSpec(
            name="business_location",
            required=False,
            input_type=InputType.TEXT,
            prompt="Which location/branch? (optional if only one location)",
            description="Business location"
        ),
        SlotSpec(
            name="cancel_reason",
            required=False,
            input_type=InputType.TEXT,
            prompt="Any reason to provide? (optional)",
            description="Cancellation reason"
        ),
        SlotSpec(
            name="reschedule_intent",
            required=False,
            input_type=InputType.YES_NO,
            prompt="Would you like to reschedule?",
            description="Whether to ask about rescheduling"
        ),
    ],

    confirm_title="Cancel Appointment",
    confirm_lines=[
        "Business: {business_name}",
        "Appointment: {appointment_day} at {appointment_time}",
        "Name on booking: {customer_name}",
    ],

    phone_source=PhoneSource.PLACE,
    place_query_slot="business_name",
    place_area_slot="business_location",

    phone_flow=PhoneFlow(
        mode=PhoneFlowMode.LLM_DIALOG,
        system_prompt_template=(
            "You are calling {business_name} to cancel an appointment. "
            "The appointment is on {appointment_day} at {appointment_time} under the name {customer_name}. "
            "Be polite, identify yourself as an AI assistant, and confirm the cancellation."
        ),
    ),

    objective_template="Cancel appointment at {business_name} on {appointment_day} at {appointment_time}",
    script_template=(
        "Call {business_name} to cancel the appointment on {appointment_day} at {appointment_time} "
        "under the name {customer_name}."
    ),
)


# =============================================================================
# REGISTRY
# =============================================================================

AGENTS: Dict[str, AgentSpec] = {
    "SICK_CALLER": SICK_CALLER_SPEC,
    "STOCK_CHECKER": STOCK_CHECKER_SPEC,
    "RESTAURANT_RESERVATION": RESTAURANT_RESERVATION_SPEC,
    "CANCEL_APPOINTMENT": CANCEL_APPOINTMENT_SPEC,
}


def get_agent_spec(agent_type: str) -> AgentSpec:
    """
    Get the AgentSpec for a given agent type.

    Raises:
        ValueError: If agent type is not found in registry.
    """
    spec = AGENTS.get(agent_type)
    if spec is None:
        raise ValueError(f"Unknown agent type: {agent_type}. Valid types: {list(AGENTS.keys())}")
    return spec
