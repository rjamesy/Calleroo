package com.calleroo.app.domain.model

import org.junit.Assert.*
import org.junit.Test

/**
 * Unit tests for ConversationModels.
 *
 * Tests cover:
 * 1. QuickReply model
 * 2. Question.getEffectiveQuickReplies() logic
 * 3. AgentMeta model
 * 4. InputType enum values
 */
class ConversationModelsTest {

    // =============================================================================
    // QuickReply Tests
    // =============================================================================

    @Test
    fun `QuickReply has correct label and value`() {
        val qr = QuickReply(label = "Yes", value = "YES")
        assertEquals("Yes", qr.label)
        assertEquals("YES", qr.value)
    }

    // =============================================================================
    // Question.getEffectiveQuickReplies() Tests
    // =============================================================================

    @Test
    fun `Question with quickReplies returns them directly`() {
        val quickReplies = listOf(
            QuickReply("Option 1", "OPT1"),
            QuickReply("Option 2", "OPT2")
        )
        val question = Question(
            text = "Pick one",
            field = "choice",
            inputType = InputType.CHOICE,
            quickReplies = quickReplies
        )

        val effective = question.getEffectiveQuickReplies()

        assertNotNull(effective)
        assertEquals(2, effective?.size)
        assertEquals("Option 1", effective?.get(0)?.label)
        assertEquals("OPT1", effective?.get(0)?.value)
    }

    @Test
    fun `Question with YES_NO type generates yes-no quick replies`() {
        val question = Question(
            text = "Do you agree?",
            field = "agreement",
            inputType = InputType.YES_NO
        )

        val effective = question.getEffectiveQuickReplies()

        assertNotNull(effective)
        assertEquals(2, effective?.size)
        assertEquals("Yes", effective?.get(0)?.label)
        assertEquals("YES", effective?.get(0)?.value)
        assertEquals("No", effective?.get(1)?.label)
        assertEquals("NO", effective?.get(1)?.value)
    }

    @Test
    fun `Question with choices falls back to converting choices`() {
        val choices = listOf(
            Choice(label = "Sick", value = "SICK"),
            Choice(label = "Carer", value = "CARER")
        )
        val question = Question(
            text = "Why?",
            field = "reason",
            inputType = InputType.CHOICE,
            choices = choices
        )

        val effective = question.getEffectiveQuickReplies()

        assertNotNull(effective)
        assertEquals(2, effective?.size)
        assertEquals("Sick", effective?.get(0)?.label)
        assertEquals("SICK", effective?.get(0)?.value)
        assertEquals("Carer", effective?.get(1)?.label)
        assertEquals("CARER", effective?.get(1)?.value)
    }

    @Test
    fun `Question with TEXT type returns null quick replies`() {
        val question = Question(
            text = "What is your name?",
            field = "name",
            inputType = InputType.TEXT
        )

        val effective = question.getEffectiveQuickReplies()

        assertNull(effective)
    }

    @Test
    fun `QuickReplies take precedence over choices`() {
        val quickReplies = listOf(
            QuickReply("QR Option", "QR_VALUE")
        )
        val choices = listOf(
            Choice(label = "Choice Option", value = "CHOICE_VALUE")
        )
        val question = Question(
            text = "Pick",
            field = "field",
            inputType = InputType.CHOICE,
            quickReplies = quickReplies,
            choices = choices
        )

        val effective = question.getEffectiveQuickReplies()

        assertNotNull(effective)
        assertEquals(1, effective?.size)
        assertEquals("QR Option", effective?.get(0)?.label)
        assertEquals("QR_VALUE", effective?.get(0)?.value)
    }

    @Test
    fun `Empty quickReplies list falls back to choices`() {
        val choices = listOf(
            Choice(label = "Choice", value = "VALUE")
        )
        val question = Question(
            text = "Pick",
            field = "field",
            inputType = InputType.CHOICE,
            quickReplies = emptyList(),
            choices = choices
        )

        val effective = question.getEffectiveQuickReplies()

        assertNotNull(effective)
        assertEquals(1, effective?.size)
        assertEquals("Choice", effective?.get(0)?.label)
    }

    // =============================================================================
    // AgentMeta Tests
    // =============================================================================

    @Test
    fun `AgentMeta with PLACE phone source`() {
        val meta = AgentMeta(
            phoneSource = "PLACE",
            directPhoneSlot = null,
            title = "Stock Check",
            description = "Check product availability"
        )

        assertEquals("PLACE", meta.phoneSource)
        assertNull(meta.directPhoneSlot)
        assertEquals("Stock Check", meta.title)
    }

    @Test
    fun `AgentMeta with DIRECT_SLOT phone source`() {
        val meta = AgentMeta(
            phoneSource = "DIRECT_SLOT",
            directPhoneSlot = "employer_phone",
            title = "Call in Sick",
            description = "Notify employer"
        )

        assertEquals("DIRECT_SLOT", meta.phoneSource)
        assertEquals("employer_phone", meta.directPhoneSlot)
        assertEquals("Call in Sick", meta.title)
    }

    @Test
    fun `AgentMeta default values`() {
        val meta = AgentMeta()

        assertEquals("PLACE", meta.phoneSource)
        assertNull(meta.directPhoneSlot)
        assertEquals("", meta.title)
        assertEquals("", meta.description)
    }

    // =============================================================================
    // InputType Tests
    // =============================================================================

    @Test
    fun `InputType has all expected values`() {
        val types = InputType.values()

        assertTrue(types.contains(InputType.TEXT))
        assertTrue(types.contains(InputType.NUMBER))
        assertTrue(types.contains(InputType.DATE))
        assertTrue(types.contains(InputType.TIME))
        assertTrue(types.contains(InputType.BOOLEAN))
        assertTrue(types.contains(InputType.CHOICE))
        assertTrue(types.contains(InputType.PHONE))
        assertTrue(types.contains(InputType.YES_NO))
    }

    // =============================================================================
    // NextAction Tests
    // =============================================================================

    @Test
    fun `NextAction has all expected values`() {
        val actions = NextAction.values()

        assertTrue(actions.contains(NextAction.ASK_QUESTION))
        assertTrue(actions.contains(NextAction.CONFIRM))
        assertTrue(actions.contains(NextAction.COMPLETE))
        assertTrue(actions.contains(NextAction.FIND_PLACE))
    }

    // =============================================================================
    // ClientAction Tests
    // =============================================================================

    @Test
    fun `ClientAction has CONFIRM and REJECT`() {
        val actions = ClientAction.values()

        assertTrue(actions.contains(ClientAction.CONFIRM))
        assertTrue(actions.contains(ClientAction.REJECT))
        assertEquals(2, actions.size)
    }

    // =============================================================================
    // ConfirmationCard Tests
    // =============================================================================

    @Test
    fun `ConfirmationCard with default labels`() {
        val card = ConfirmationCard(
            title = "Confirm Details",
            lines = listOf("Line 1", "Line 2")
        )

        assertEquals("Confirm Details", card.title)
        assertEquals(2, card.lines.size)
        assertEquals("Yes", card.confirmLabel)
        assertEquals("Not quite", card.rejectLabel)
        assertNull(card.cardId)
    }

    @Test
    fun `ConfirmationCard with custom labels`() {
        val card = ConfirmationCard(
            title = "Ready?",
            lines = listOf("Item 1"),
            confirmLabel = "Let's go!",
            rejectLabel = "Wait",
            cardId = "card-123"
        )

        assertEquals("Let's go!", card.confirmLabel)
        assertEquals("Wait", card.rejectLabel)
        assertEquals("card-123", card.cardId)
    }

    // =============================================================================
    // 5.2 QuickReplies + Typing Disable Tests (Checklist item)
    // =============================================================================

    @Test
    fun `CHOICE type returns quickReplies - indicates typing should be disabled in UI`() {
        // Checklist 5.2: When inputType == CHOICE, quickReplies are present
        // This signals to the UI that the user should use chips instead of typing
        val question = Question(
            text = "What's the reason?",
            field = "reason_category",
            inputType = InputType.CHOICE,
            choices = listOf(
                Choice(label = "Sick", value = "SICK"),
                Choice(label = "Carer", value = "CARER")
            )
        )

        val quickReplies = question.getEffectiveQuickReplies()

        // QuickReplies are present for CHOICE type
        assertNotNull(quickReplies)
        assertTrue(quickReplies!!.isNotEmpty())
        assertEquals(2, quickReplies.size)
    }

    @Test
    fun `YES_NO type returns quickReplies - indicates typing should be disabled in UI`() {
        // Same as CHOICE: YES_NO implies use quickReply chips
        val question = Question(
            text = "Do you want to share contact?",
            field = "share_contact",
            inputType = InputType.YES_NO
        )

        val quickReplies = question.getEffectiveQuickReplies()

        assertNotNull(quickReplies)
        assertEquals(2, quickReplies!!.size)
        assertEquals("Yes", quickReplies[0].label)
        assertEquals("No", quickReplies[1].label)
    }

    @Test
    fun `TEXT type returns null quickReplies - indicates typing should be enabled`() {
        // TEXT type = no quickReplies, user should type
        val question = Question(
            text = "What's your name?",
            field = "caller_name",
            inputType = InputType.TEXT
        )

        val quickReplies = question.getEffectiveQuickReplies()

        // No quickReplies for TEXT - typing is appropriate
        assertNull(quickReplies)
    }

    @Test
    fun `PHONE type returns null quickReplies - indicates typing should be enabled`() {
        val question = Question(
            text = "Phone number?",
            field = "employer_phone",
            inputType = InputType.PHONE
        )

        val quickReplies = question.getEffectiveQuickReplies()

        assertNull(quickReplies)
    }

    // =============================================================================
    // PlaceSearchParams Tests
    // =============================================================================

    @Test
    fun `PlaceSearchParams with default country`() {
        val params = PlaceSearchParams(
            query = "JB Hi-Fi",
            area = "Sydney"
        )

        assertEquals("JB Hi-Fi", params.query)
        assertEquals("Sydney", params.area)
        assertEquals("AU", params.country)
    }

    @Test
    fun `PlaceSearchParams with custom country`() {
        val params = PlaceSearchParams(
            query = "Store",
            area = "Auckland",
            country = "NZ"
        )

        assertEquals("NZ", params.country)
    }
}
