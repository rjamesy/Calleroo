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
    PHONE
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

@Serializable
data class Choice(
    val label: String,
    val value: String
)

@Serializable
data class Question(
    val text: String = "",
    val field: String = "",
    val inputType: InputType = InputType.TEXT,
    val choices: List<Choice>? = null,
    val optional: Boolean = false
)

@Serializable
data class ConfirmationCard(
    val title: String = "",
    val lines: List<String> = emptyList(),
    val confirmLabel: String = "Yes",
    val rejectLabel: String = "Not quite"
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
    val debug: Boolean = false
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
    val aiCallMade: Boolean = false,
    val aiModel: String = ""
)
