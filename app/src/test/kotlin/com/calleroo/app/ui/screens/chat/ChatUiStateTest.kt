package com.calleroo.app.ui.screens.chat

import com.calleroo.app.domain.model.AgentMeta
import com.calleroo.app.domain.model.AgentType
import com.calleroo.app.domain.model.ConfirmationCard
import com.calleroo.app.domain.model.NextAction
import com.calleroo.app.domain.model.PlaceSearchParams
import com.calleroo.app.domain.model.Question
import com.calleroo.app.domain.model.InputType
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for ChatUiState.
 *
 * Tests cover:
 * 1. showConfirmationCard computed property
 * 2. showContinueButton computed property
 * 3. State initialization
 * 4. agentMeta handling
 */
class ChatUiStateTest {

    // =============================================================================
    // showConfirmationCard Tests
    // =============================================================================

    @Test
    fun `showConfirmationCard is true when CONFIRM action with card`() {
        val state = ChatUiState(
            nextAction = NextAction.CONFIRM,
            confirmationCard = ConfirmationCard(
                title = "Confirm",
                lines = listOf("Line 1")
            )
        )

        assertTrue(state.showConfirmationCard)
    }

    @Test
    fun `showConfirmationCard is false when CONFIRM action without card`() {
        val state = ChatUiState(
            nextAction = NextAction.CONFIRM,
            confirmationCard = null
        )

        assertFalse(state.showConfirmationCard)
    }

    @Test
    fun `showConfirmationCard is false when ASK_QUESTION action`() {
        val state = ChatUiState(
            nextAction = NextAction.ASK_QUESTION,
            confirmationCard = ConfirmationCard(
                title = "Confirm",
                lines = listOf("Line 1")
            )
        )

        assertFalse(state.showConfirmationCard)
    }

    @Test
    fun `showConfirmationCard is false when action is null`() {
        val state = ChatUiState(
            nextAction = null,
            confirmationCard = ConfirmationCard(
                title = "Confirm",
                lines = listOf("Line 1")
            )
        )

        assertFalse(state.showConfirmationCard)
    }

    // =============================================================================
    // showContinueButton Tests
    // =============================================================================

    @Test
    fun `showContinueButton is true when COMPLETE and isComplete`() {
        val state = ChatUiState(
            nextAction = NextAction.COMPLETE,
            isComplete = true
        )

        assertTrue(state.showContinueButton)
    }

    @Test
    fun `showContinueButton is false when COMPLETE but not isComplete`() {
        val state = ChatUiState(
            nextAction = NextAction.COMPLETE,
            isComplete = false
        )

        assertFalse(state.showContinueButton)
    }

    @Test
    fun `showContinueButton is true when FIND_PLACE with params`() {
        val state = ChatUiState(
            nextAction = NextAction.FIND_PLACE,
            placeSearchParams = PlaceSearchParams(
                query = "Store",
                area = "Sydney"
            )
        )

        assertTrue(state.showContinueButton)
    }

    @Test
    fun `showContinueButton is false when FIND_PLACE without params`() {
        val state = ChatUiState(
            nextAction = NextAction.FIND_PLACE,
            placeSearchParams = null
        )

        assertFalse(state.showContinueButton)
    }

    @Test
    fun `showContinueButton is false when ASK_QUESTION`() {
        val state = ChatUiState(
            nextAction = NextAction.ASK_QUESTION
        )

        assertFalse(state.showContinueButton)
    }

    @Test
    fun `showContinueButton is false when CONFIRM`() {
        val state = ChatUiState(
            nextAction = NextAction.CONFIRM,
            confirmationCard = ConfirmationCard(
                title = "Confirm",
                lines = listOf("Line 1")
            )
        )

        assertFalse(state.showContinueButton)
    }

    // =============================================================================
    // State Initialization Tests
    // =============================================================================

    @Test
    fun `default state has expected values`() {
        val state = ChatUiState()

        assertEquals("", state.conversationId)
        assertEquals(AgentType.STOCK_CHECKER, state.agentType)
        assertTrue(state.messages.isEmpty())
        assertTrue(state.slots.isEmpty())
        assertNull(state.currentQuestion)
        assertNull(state.confirmationCard)
        assertNull(state.nextAction)
        assertFalse(state.isLoading)
        assertFalse(state.isConfirmationSubmitting)
        assertNull(state.error)
        assertFalse(state.isComplete)
        assertNull(state.placeSearchParams)
        assertNull(state.agentMeta)
    }

    @Test
    fun `state with slots`() {
        val slots = buildJsonObject {
            put("employer_name", "Bunnings")
            put("employer_phone", "+61412345678")
        }

        val state = ChatUiState(
            conversationId = "test-123",
            agentType = AgentType.SICK_CALLER,
            slots = slots
        )

        assertEquals("test-123", state.conversationId)
        assertEquals(AgentType.SICK_CALLER, state.agentType)
        assertEquals(2, state.slots.size)
    }

    // =============================================================================
    // agentMeta Tests
    // =============================================================================

    @Test
    fun `state with PLACE agentMeta`() {
        val meta = AgentMeta(
            phoneSource = "PLACE",
            directPhoneSlot = null,
            title = "Stock Check",
            description = "Check availability"
        )

        val state = ChatUiState(
            agentMeta = meta
        )

        assertNotNull(state.agentMeta)
        assertEquals("PLACE", state.agentMeta?.phoneSource)
        assertNull(state.agentMeta?.directPhoneSlot)
    }

    @Test
    fun `state with DIRECT_SLOT agentMeta`() {
        val meta = AgentMeta(
            phoneSource = "DIRECT_SLOT",
            directPhoneSlot = "employer_phone",
            title = "Call in Sick",
            description = "Notify employer"
        )

        val state = ChatUiState(
            agentMeta = meta
        )

        assertNotNull(state.agentMeta)
        assertEquals("DIRECT_SLOT", state.agentMeta?.phoneSource)
        assertEquals("employer_phone", state.agentMeta?.directPhoneSlot)
    }

    // =============================================================================
    // Messages Tests
    // =============================================================================

    @Test
    fun `state with messages`() {
        val messages = listOf(
            ChatMessageUi(
                id = "1",
                content = "Hello",
                isUser = false
            ),
            ChatMessageUi(
                id = "2",
                content = "Hi there!",
                isUser = true
            )
        )

        val state = ChatUiState(
            messages = messages
        )

        assertEquals(2, state.messages.size)
        assertFalse(state.messages[0].isUser)
        assertTrue(state.messages[1].isUser)
    }

    // =============================================================================
    // Error State Tests
    // =============================================================================

    @Test
    fun `state with error`() {
        val state = ChatUiState(
            error = "Network error occurred"
        )

        assertNotNull(state.error)
        assertEquals("Network error occurred", state.error)
    }

    // =============================================================================
    // Loading State Tests
    // =============================================================================

    @Test
    fun `state with loading`() {
        val state = ChatUiState(
            isLoading = true
        )

        assertTrue(state.isLoading)
    }

    @Test
    fun `state with confirmation submitting`() {
        val state = ChatUiState(
            isConfirmationSubmitting = true,
            confirmationCard = ConfirmationCard(
                title = "Confirm",
                lines = listOf("Line 1")
            )
        )

        assertTrue(state.isConfirmationSubmitting)
    }
}
