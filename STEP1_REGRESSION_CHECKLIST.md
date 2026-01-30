# Regression Checklist

This checklist verifies the v2 architecture with unified OpenAI-driven conversation loop and Place Search.

---

## Step 1 - Conversation Flow Baseline

## Pre-requisites

- [ ] Backend running: `cd backend_v2 && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- [ ] OpenAI API key configured in `backend_v2/.env`
- [ ] Android app built and running on emulator (uses 10.0.2.2:8000)

---

## Stock Checker Flow

### Initial Setup
- [ ] Launch app - AgentSelectScreen appears
- [ ] "Stock Check" tile is visible
- [ ] "Book Restaurant" tile is visible
- [ ] Continue button is disabled when no tile selected

### Agent Selection
- [ ] Tap "Stock Check" tile - tile becomes highlighted
- [ ] Continue button becomes enabled
- [ ] Tap Continue - navigates to UnifiedChatScreen
- [ ] Top bar shows "Stock Check"

### Conversation Flow
- [ ] Assistant sends initial greeting asking for retailer
- [ ] User types retailer name (e.g., "JB Hi-Fi") and sends
- [ ] Assistant extracts retailer and asks for store location
- [ ] User provides location (e.g., "Richmond")
- [ ] Assistant asks for product name
- [ ] User provides product (e.g., "Sony headphones")
- [ ] Assistant may ask for brand/model/variant (optional fields)
- [ ] User can say "skip" for optional fields
- [ ] **CRITICAL**: Skipped fields are NOT re-asked
- [ ] Assistant asks for quantity
- [ ] User provides quantity

### Confirmation
- [ ] When all required info collected, backend returns CONFIRM
- [ ] Confirmation card appears with:
  - [ ] Title: "Stock Check Request"
  - [ ] Lines listing: Retailer, Location, Product, etc.
  - [ ] "Yes, that's right" button
  - [ ] "Not quite" button

### Confirm - Accept
- [ ] Tap "Yes, that's right"
- [ ] Backend returns COMPLETE
- [ ] Assistant shows completion message
- [ ] "Continue" button appears
- [ ] Tap Continue - logs "NEXT_SCREEN_NOT_IMPLEMENTED"

### Confirm - Reject
- [ ] Tap "Not quite"
- [ ] Assistant asks what needs to be changed
- [ ] User can provide correction
- [ ] Flow continues appropriately

---

## Restaurant Reservation Flow

### Agent Selection
- [ ] From AgentSelectScreen, tap "Book Restaurant" tile
- [ ] Continue -> navigates to UnifiedChatScreen
- [ ] Top bar shows "Book Restaurant"

### Conversation Flow
- [ ] Assistant sends initial greeting asking for restaurant
- [ ] User provides restaurant name (e.g., "The Italian Place")
- [ ] Assistant asks for suburb/area
- [ ] User provides location (e.g., "South Yarra")
- [ ] Assistant asks for party size (may show choice chips)
- [ ] **Choice chips render ONLY when backend sends them**
- [ ] User selects party size
- [ ] Assistant asks for date
- [ ] User provides date
- [ ] Assistant asks for time
- [ ] User provides time
- [ ] Assistant may ask about sharing contact (boolean, optional)
- [ ] User can skip

### Confirmation
- [ ] When all required info collected, backend returns CONFIRM
- [ ] Confirmation card appears with:
  - [ ] Title: "Reservation Details"
  - [ ] Lines: Restaurant, Location, Party size, Date, Time
  - [ ] Confirm/Reject buttons

### Complete
- [ ] Tap confirm -> backend returns COMPLETE
- [ ] Assistant shows completion message
- [ ] Continue button appears

---

## Critical Behavioral Checks

### Backend Authority
- [ ] **Android NEVER decides question order** - all questions come from backend
- [ ] **Android NEVER generates choice chips locally** - only renders what backend sends
- [ ] **aiCallMade is always true** in all responses
- [ ] **aiModel field is populated** in all responses

### No Repeated Questions
- [ ] If user provides info in initial message, backend doesn't re-ask
- [ ] If user says "skip", backend moves on and doesn't re-ask
- [ ] If user declines a field, backend doesn't loop back to it

### Error Handling
- [ ] If backend is down, error snackbar appears
- [ ] If network timeout, error snackbar appears
- [ ] App doesn't crash on network errors

### Debug Guard
- [ ] In debug builds, UnifiedConversationGuard is active
- [ ] If any local question logic were invoked, app would crash
- [ ] Guard validates aiCallMade == true on every response

---

## Backend Tests

Run from `backend_v2/` directory:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v
```

### Test Cases
- [ ] `test_stock_checker_initial_turn` - passes
- [ ] `test_restaurant_reservation_initial_turn` - passes
- [ ] `test_stock_checker_with_user_message` - passes
- [ ] `test_restaurant_reservation_with_user_message` - passes
- [ ] `test_confirm_action_has_confirmation_card` - passes
- [ ] `test_health_check` - passes

---

## Architecture Compliance

### Hard Rules Verification
- [ ] Android client does NOT decide questions, slots, flow order
- [ ] Backend (OpenAI) is sole authority for all conversation decisions
- [ ] Backend calls OpenAI on EVERY turn (no caching)
- [ ] Debug builds have runtime guard that would crash on local logic
- [ ] Step 1 does NOT implement Places/Twilio/Summary screen

### Code Structure
- [ ] Backend in `backend_v2/` folder (clean, separate from any legacy)
- [ ] Android screens in `com.calleroo.app.ui.screens`
- [ ] No legacy screens reused
- [ ] No old logic ported

---

## Sign-off

| Tester | Date | Pass/Fail | Notes |
|--------|------|-----------|-------|
|        |      |           |       |

---

## Known Limitations (Step 1)

1. **No Google Places lookup** - only collects restaurant/retailer names
2. **No Twilio integration** - no actual calls made
3. **No Summary screen** - "Continue" just logs placeholder
4. **No persistence** - conversation lost on app restart
5. **No offline support** - requires network connection

---

# Step 2 - Place Search Screen

## Pre-requisites

- [ ] Step 1 checks pass
- [ ] Google Places API key configured in `backend_v2/.env` as `GOOGLE_PLACES_API_KEY`
- [ ] Backend shows "Google Places service initialized" on startup

---

## Stock Checker → Place Search Flow

### Trigger FIND_PLACE
- [ ] Complete Stock Checker flow to confirmation
- [ ] Tap "Yes" to confirm
- [ ] Backend returns `nextAction=FIND_PLACE` with `placeSearchParams`
- [ ] App navigates to PlaceSearchScreen
- [ ] PlaceSearchScreen shows "Choose the place to call" title
- [ ] Subtitle shows "Searching for {retailer} near {location}"

### Search Results
- [ ] Loading spinner shown initially
- [ ] Places load with 25km default radius
- [ ] Results count shown: "Found X places within 25km"
- [ ] Each place shows name and address
- [ ] Tap a place card → card becomes selected (highlighted, checkmark)
- [ ] "Use this place" button is disabled until selection made
- [ ] "Search wider" button visible (if radius < 100km)

### Expand Radius
- [ ] Tap "Search wider (50km)" → re-searches with 50km radius
- [ ] Results update with new radius
- [ ] Button changes to "Search wider (100km)"
- [ ] At 100km, "Search wider" button disappears
- [ ] **User must explicitly tap expand** - no automatic expansion

### Resolve Place
- [ ] Select a place and tap "Use this place"
- [ ] Loading: "Fetching details for {placeName}..."
- [ ] Resolved state shows:
  - [ ] Checkmark icon
  - [ ] Business name
  - [ ] Address
  - [ ] Phone number (E.164 format)
- [ ] "Continue" button appears

### Place Without Phone
- [ ] If selected place has no valid phone number:
- [ ] Error state shows "Something went wrong"
- [ ] "Back to results" button allows picking another place
- [ ] User can select a different place

### Navigation
- [ ] Back arrow returns to chat screen
- [ ] Tapping "Continue" on resolved place logs and pops back (Step 2 stop point)

---

## Restaurant Reservation → Place Search Flow

### Trigger FIND_PLACE
- [ ] Complete Restaurant Reservation flow to confirmation
- [ ] Tap "Yes" to confirm
- [ ] Backend returns `nextAction=FIND_PLACE` with `placeSearchParams`
- [ ] App navigates to PlaceSearchScreen
- [ ] Subtitle shows "Searching for {restaurant} near {suburb}"

### Same Place Search UX
- [ ] All place search checks from Stock Checker apply here
- [ ] Search uses restaurant name and area

---

## No Results Handling

- [ ] If search returns 0 results at 25km:
- [ ] "No places found" message shown
- [ ] "Search wider (50km)" button available
- [ ] Expanding to 50km/100km may find results
- [ ] At 100km with no results, only "Back to chat" shown

---

## Critical Behavioral Checks (Step 2)

### Deterministic Place Search
- [ ] **Places endpoints do NOT call OpenAI** - deterministic Google Places only
- [ ] `/places/search` uses Text Search API with area geocoding
- [ ] `/places/details` fetches phone number and details
- [ ] Area geocoding provides location bias (NOT GPS)

### No GPS / Location Services
- [ ] App does NOT request location permissions
- [ ] Area is passed from chat (suburb/city name)
- [ ] Geocoding converts area name to lat/lng for search

### Phone Number Validation
- [ ] Only places with valid E.164 phone can proceed
- [ ] Places without phone show error when resolved
- [ ] E.164 format: +61412345678 (Australian example)

### Radius Control
- [ ] Default radius is 25km
- [ ] Radius only increases when user taps expand
- [ ] Valid radii: 25, 50, 100 km only
- [ ] No automatic radius expansion

---

## Backend Place Endpoints Tests

```bash
# Test place search
curl -X POST http://localhost:8000/places/search \
  -H "Content-Type: application/json" \
  -d '{"query": "JB Hi-Fi", "area": "Richmond VIC", "radiusKm": 25}'

# Test place details
curl -X POST http://localhost:8000/places/details \
  -H "Content-Type: application/json" \
  -d '{"placeId": "ChIJ..."}'
```

- [ ] `/places/search` returns candidates with placeId, name, address
- [ ] `/places/details` returns phoneE164 for valid places
- [ ] `/places/details` returns `error="NO_PHONE"` for places without phone

---

## Sign-off (Step 2)

| Tester | Date | Pass/Fail | Notes |
|--------|------|-----------|-------|
|        |      |           |       |

---

## Known Limitations (Step 2)

1. **No Call/Summary screen** - "Continue" on resolved place logs placeholder
2. **No Twilio integration** - phone number collected but not dialed
3. **No place caching** - searches always hit Google API
4. **Area geocoding only** - no GPS fallback if area lookup fails
