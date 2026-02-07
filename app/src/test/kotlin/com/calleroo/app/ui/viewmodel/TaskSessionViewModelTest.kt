package com.calleroo.app.ui.viewmodel

import com.calleroo.app.domain.model.AgentType
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * JVM unit tests for TaskSessionViewModel.
 *
 * Tests cover checklist item 5.1:
 * - Slot merge behavior (CRITICAL: slots must never be lost)
 * - Session initialization idempotency
 * - Resolved place state management
 */
class TaskSessionViewModelTest {

    private lateinit var viewModel: TaskSessionViewModel

    @Before
    fun setUp() {
        viewModel = TaskSessionViewModel()
    }

    // =============================================================================
    // 5.1 Slot Merge Tests (CRITICAL)
    // =============================================================================

    @Test
    fun `updateSlots merges new slots with existing slots`() {
        viewModel.initSession("conv-1", AgentType.SICK_CALLER)

        // First update: set employer_name
        val slots1 = buildJsonObject {
            put("employer_name", JsonPrimitive("Bunnings"))
        }
        viewModel.updateSlots(slots1)

        // Second update: set caller_name (different key)
        val slots2 = buildJsonObject {
            put("caller_name", JsonPrimitive("Richard"))
        }
        viewModel.updateSlots(slots2)

        // Both slots must exist
        val merged = viewModel.slots.value
        assertEquals("Bunnings", (merged["employer_name"] as JsonPrimitive).content)
        assertEquals("Richard", (merged["caller_name"] as JsonPrimitive).content)
    }

    @Test
    fun `updateSlots never loses existing slots when incoming is empty`() {
        viewModel.initSession("conv-2", AgentType.SICK_CALLER)

        // Set several slots
        val initialSlots = buildJsonObject {
            put("employer_name", JsonPrimitive("JB Hi-Fi"))
            put("employer_phone", JsonPrimitive("+61400000000"))
            put("caller_name", JsonPrimitive("Alice"))
        }
        viewModel.updateSlots(initialSlots)

        // Backend returns empty extractedData (simulates null response)
        val emptySlots = buildJsonObject {}
        viewModel.updateSlots(emptySlots)

        // All original slots must still exist
        val current = viewModel.slots.value
        assertEquals(3, current.keys.size)
        assertEquals("JB Hi-Fi", (current["employer_name"] as JsonPrimitive).content)
        assertEquals("+61400000000", (current["employer_phone"] as JsonPrimitive).content)
        assertEquals("Alice", (current["caller_name"] as JsonPrimitive).content)
    }

    @Test
    fun `updateSlots overwrites existing key with new value`() {
        viewModel.initSession("conv-3", AgentType.STOCK_CHECKER)

        val slots1 = buildJsonObject {
            put("quantity", JsonPrimitive("2"))
        }
        viewModel.updateSlots(slots1)

        // User corrects the quantity
        val slots2 = buildJsonObject {
            put("quantity", JsonPrimitive("5"))
        }
        viewModel.updateSlots(slots2)

        val current = viewModel.slots.value
        assertEquals("5", (current["quantity"] as JsonPrimitive).content)
    }

    @Test
    fun `updateSlots preserves slots across multiple turns`() {
        viewModel.initSession("conv-4", AgentType.SICK_CALLER)

        // Turn 1: employer_name
        viewModel.updateSlots(buildJsonObject {
            put("employer_name", JsonPrimitive("Employer"))
        })

        // Turn 2: employer_phone
        viewModel.updateSlots(buildJsonObject {
            put("employer_phone", JsonPrimitive("+61400000001"))
        })

        // Turn 3: caller_name
        viewModel.updateSlots(buildJsonObject {
            put("caller_name", JsonPrimitive("Bob"))
        })

        // Turn 4: shift_date
        viewModel.updateSlots(buildJsonObject {
            put("shift_date", JsonPrimitive("tomorrow"))
        })

        // Turn 5: shift_start_time
        viewModel.updateSlots(buildJsonObject {
            put("shift_start_time", JsonPrimitive("9am"))
        })

        // Turn 6: reason_category
        viewModel.updateSlots(buildJsonObject {
            put("reason_category", JsonPrimitive("SICK"))
        })

        // ALL 6 slots must exist
        val current = viewModel.slots.value
        assertEquals(6, current.keys.size)
        assertTrue(current.containsKey("employer_name"))
        assertTrue(current.containsKey("employer_phone"))
        assertTrue(current.containsKey("caller_name"))
        assertTrue(current.containsKey("shift_date"))
        assertTrue(current.containsKey("shift_start_time"))
        assertTrue(current.containsKey("reason_category"))
    }

    @Test
    fun `updateSlots handles null-like scenario from backend`() {
        viewModel.initSession("conv-5", AgentType.SICK_CALLER)

        // Simulate 3 turns of slot collection
        viewModel.updateSlots(buildJsonObject {
            put("employer_name", JsonPrimitive("Test Corp"))
        })
        viewModel.updateSlots(buildJsonObject {
            put("employer_phone", JsonPrimitive("+61400000002"))
        })
        viewModel.updateSlots(buildJsonObject {
            put("caller_name", JsonPrimitive("Charlie"))
        })

        // Backend returns response with only new slot (simulates partial extraction)
        // This could happen if backend only extracts new data
        viewModel.updateSlots(buildJsonObject {
            put("shift_date", JsonPrimitive("2024-01-15"))
        })

        // All 4 slots must exist (merge, not replace)
        val current = viewModel.slots.value
        assertEquals(4, current.keys.size)
        assertEquals("Test Corp", (current["employer_name"] as JsonPrimitive).content)
        assertEquals("Charlie", (current["caller_name"] as JsonPrimitive).content)
        assertEquals("2024-01-15", (current["shift_date"] as JsonPrimitive).content)
    }

    // =============================================================================
    // Session Initialization Tests
    // =============================================================================

    @Test
    fun `initSession is idempotent for same conversationId`() {
        viewModel.initSession("conv-idem", AgentType.SICK_CALLER)

        // Set some slots
        viewModel.updateSlots(buildJsonObject {
            put("employer_name", JsonPrimitive("Idempotent Corp"))
        })

        // Re-init with same conversationId (e.g., on recomposition)
        viewModel.initSession("conv-idem", AgentType.SICK_CALLER)

        // Slots must NOT be reset
        val current = viewModel.slots.value
        assertEquals(1, current.keys.size)
        assertEquals("Idempotent Corp", (current["employer_name"] as JsonPrimitive).content)
    }

    @Test
    fun `initSession resets state for different conversationId`() {
        viewModel.initSession("conv-old", AgentType.SICK_CALLER)
        viewModel.updateSlots(buildJsonObject {
            put("employer_name", JsonPrimitive("Old Corp"))
        })

        // Init with NEW conversationId
        viewModel.initSession("conv-new", AgentType.STOCK_CHECKER)

        // Slots must be reset
        val current = viewModel.slots.value
        assertEquals(0, current.keys.size)
        assertEquals(AgentType.STOCK_CHECKER, viewModel.agentType)
        assertEquals("conv-new", viewModel.conversationId)
    }

    @Test
    fun `initSession sets agentType correctly`() {
        viewModel.initSession("conv-agent", AgentType.RESTAURANT_RESERVATION)
        assertEquals(AgentType.RESTAURANT_RESERVATION, viewModel.agentType)

        // New session with different agent type
        viewModel.initSession("conv-agent-2", AgentType.CANCEL_APPOINTMENT)
        assertEquals(AgentType.CANCEL_APPOINTMENT, viewModel.agentType)
    }

    // =============================================================================
    // Resolved Place Tests
    // =============================================================================

    @Test
    fun `setResolvedPlace stores place correctly`() {
        viewModel.initSession("conv-place", AgentType.STOCK_CHECKER)

        val place = com.calleroo.app.domain.model.ResolvedPlace(
            placeId = "place-123",
            businessName = "JB Hi-Fi Sydney",
            formattedAddress = "123 George St, Sydney NSW 2000",
            phoneE164 = "+61299998888"
        )
        viewModel.setResolvedPlace(place)

        assertEquals(place, viewModel.resolvedPlace.value)
        assertEquals("place-123", viewModel.resolvedPlace.value?.placeId)
        assertEquals("+61299998888", viewModel.resolvedPlace.value?.phoneE164)
    }

    @Test
    fun `clearResolvedPlace removes place`() {
        viewModel.initSession("conv-clear", AgentType.STOCK_CHECKER)

        val place = com.calleroo.app.domain.model.ResolvedPlace(
            placeId = "place-456",
            businessName = "Harvey Norman",
            formattedAddress = "456 Pitt St, Sydney NSW 2000",
            phoneE164 = "+61299997777"
        )
        viewModel.setResolvedPlace(place)
        assertNotNull(viewModel.resolvedPlace.value)

        viewModel.clearResolvedPlace()
        assertNull(viewModel.resolvedPlace.value)
    }

    @Test
    fun `initSession clears resolvedPlace for new conversation`() {
        viewModel.initSession("conv-place-old", AgentType.STOCK_CHECKER)
        viewModel.setResolvedPlace(
            com.calleroo.app.domain.model.ResolvedPlace(
                placeId = "old-place",
                businessName = "Old Store",
                formattedAddress = "Old Address",
                phoneE164 = "+61400000003"
            )
        )

        // New conversation should clear place
        viewModel.initSession("conv-place-new", AgentType.RESTAURANT_RESERVATION)
        assertNull(viewModel.resolvedPlace.value)
    }
}
