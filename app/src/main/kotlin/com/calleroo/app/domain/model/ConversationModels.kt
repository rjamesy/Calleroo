package com.calleroo.app.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
enum class NextAction {
    @SerialName("ASK_QUESTION")
    ASK_QUESTION,

    @SerialName("CONFIRM")
    CONFIRM,

    @SerialName("COMPLETE")
    COMPLETE,

    @SerialName("FIND_PLACE")
    FIND_PLACE
}

@Serializable
enum class InputType {
    @SerialName("TEXT")
    TEXT,

    @SerialName("NUMBER")
    NUMBER,

    @SerialName("DATE")
    DATE,

    @SerialName("TIME")
    TIME,

    @SerialName("BOOLEAN")
    BOOLEAN,

    @SerialName("CHOICE")
    CHOICE,

    @SerialName("PHONE")
    PHONE,

    @SerialName("YES_NO")
    YES_NO
}

@Serializable
enum class Confidence {
    @SerialName("LOW")
    LOW,

    @SerialName("MEDIUM")
    MEDIUM,

    @SerialName("HIGH")
    HIGH
}

/**
 * Client-initiated actions that bypass OpenAI for deterministic handling.
 */
@Serializable
enum class ClientAction {
    @SerialName("CONFIRM")
    CONFIRM,  // User tapped "Yes, call them"

    @SerialName("REJECT")
    REJECT    // User tapped "Not quite"
}

@Serializable
data class Choice(
    val label: String,
    val value: String
)

/**
 * Universal quick reply for UI chips (replaces choices for consistency).
 */
@Serializable
data class QuickReply(
    val label: String,
    val value: String
)

@Serializable
data class Question(
    val text: String = "",
    val field: String = "",
    val inputType: InputType = InputType.TEXT,
    val choices: List<Choice>? = null,  // Legacy: kept for compatibility
    val quickReplies: List<QuickReply>? = null,  // New: unified UI chips
    val optional: Boolean = false
) {
    /**
     * Get quick replies for this question, preferring quickReplies over choices.
     * Generates YES/NO quick replies for YES_NO input type if not provided.
     */
    fun getEffectiveQuickReplies(): List<QuickReply>? {
        // Prefer quickReplies if available
        if (!quickReplies.isNullOrEmpty()) {
            return quickReplies
        }

        // Generate YES/NO for YES_NO input type
        if (inputType == InputType.YES_NO) {
            return listOf(
                QuickReply(label = "Yes", value = "YES"),
                QuickReply(label = "No", value = "NO")
            )
        }

        // Fall back to choices (convert to QuickReply)
        if (!choices.isNullOrEmpty()) {
            return choices.map { QuickReply(label = it.label, value = it.value) }
        }

        return null
    }
}

@Serializable
data class ConfirmationCard(
    val title: String = "",
    val lines: List<String> = emptyList(),
    val confirmLabel: String = "Yes",
    val rejectLabel: String = "Not quite",
    // Stable ID for idempotency (hash of card content if not provided by backend)
    val cardId: String? = null
)

/**
 * Parameters for place search, returned with FIND_PLACE action.
 */
@Serializable
data class PlaceSearchParams(
    val query: String = "",
    val area: String = "",
    val country: String = "AU"
)

@Serializable
data class ChatMessage(
    val role: String,
    val content: String
)

@Serializable
data class ConversationRequest(
    val conversationId: String,
    val agentType: AgentType,
    val userMessage: String,
    val slots: JsonObject,
    val messageHistory: List<ChatMessage>,
    val debug: Boolean = false,
    // Optional client action for deterministic handling (bypasses OpenAI)
    val clientAction: ClientAction? = null,
    // Idempotency key to prevent duplicate actions (e.g., double-tap confirm)
    val idempotencyKey: String? = null,
    // Current question slot name (for targeted extraction)
    val currentQuestionSlotName: String? = null
)

/**
 * Agent metadata for generic UI handling.
 */
@Serializable
data class AgentMeta(
    val phoneSource: String = "PLACE",  // "PLACE" or "DIRECT_SLOT"
    val directPhoneSlot: String? = null,  // Slot name if phoneSource == "DIRECT_SLOT"
    val title: String = "",
    val description: String = ""
)

@Serializable
data class ConversationResponse(
    val assistantMessage: String = "",
    val nextAction: NextAction = NextAction.ASK_QUESTION,
    val question: Question? = null,
    val extractedData: JsonObject? = null,
    val confidence: Confidence = Confidence.MEDIUM,
    val confirmationCard: ConfirmationCard? = null,
    val placeSearchParams: PlaceSearchParams? = null,
    val agentMeta: AgentMeta? = null,  // Agent metadata for generic UI
    val aiCallMade: Boolean = false,
    val aiModel: String = ""
)
