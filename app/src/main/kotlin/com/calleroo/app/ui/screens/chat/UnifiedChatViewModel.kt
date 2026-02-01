package com.calleroo.app.ui.screens.chat

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calleroo.app.domain.model.AgentType
import com.calleroo.app.domain.model.ChatMessage
import com.calleroo.app.domain.model.ConversationResponse
import com.calleroo.app.domain.model.NextAction
import com.calleroo.app.repository.ConversationRepository
import com.calleroo.app.util.UnifiedConversationGuard
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class UnifiedChatViewModel @Inject constructor(
    private val conversationRepository: ConversationRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    // Navigation event for Continue button - triggers navigation to PlaceSearch
    private val _navigateToPlaceSearch = MutableStateFlow<Pair<String, String>?>(null)
    val navigateToPlaceSearch: StateFlow<Pair<String, String>?> = _navigateToPlaceSearch.asStateFlow()

    private var messageHistory: MutableList<ChatMessage> = mutableListOf()

    companion object {
        private const val TAG = "UnifiedChatViewModel"
        private const val START_TOKEN = "__START__"
    }

    /**
     * Initialize the conversation with given parameters.
     * Immediately calls backend to get the first question.
     */
    fun initialize(agentType: AgentType, conversationId: String) {
        _uiState.update {
            it.copy(
                conversationId = conversationId,
                agentType = agentType
            )
        }

        // Start conversation by requesting the first assistant message (no user bubble/history)
        sendMessage(START_TOKEN)
    }

    /**
     * Send a user message to the backend.
     *
     * CRITICAL: This method does NO local logic.
     * It ONLY posts to /conversation/next and renders the response.
     */
    fun sendMessage(userMessage: String) {
        val isStart = userMessage == START_TOKEN
        if (userMessage.isBlank() && !isStart) return

        // Add user message to UI/history only when not start
        if (!isStart) {
            val userMessageUi = ChatMessageUi(
                id = UUID.randomUUID().toString(),
                content = userMessage,
                isUser = true
            )
            _uiState.update { it.copy(messages = it.messages + userMessageUi) }

            messageHistory.add(ChatMessage(role = "user", content = userMessage))
        }

        _uiState.update {
            it.copy(
                isLoading = true,
                error = null,
                currentQuestion = null,
                confirmationCard = null
            )
        }

        viewModelScope.launch {
            // Always take the latest state for the request (avoid stale snapshot)
            val stateForRequest = _uiState.value

            val outboundMessage = if (isStart) "" else userMessage

            val result = conversationRepository.nextTurn(
                conversationId = stateForRequest.conversationId,
                agentType = stateForRequest.agentType,
                userMessage = outboundMessage,
                slots = stateForRequest.slots,
                messageHistory = messageHistory.toList(),
                debug = true
            )

            result.fold(
                onSuccess = { response ->
                    // CRITICAL: Verify backend drove this response
                    UnifiedConversationGuard.assertBackendDriven(response.aiCallMade)

                    // Logging for debugging (non-PII)
                    Log.d(TAG, "Backend response: action=${response.nextAction}, aiModel=${response.aiModel}")
                    Log.d(TAG, "  question.field=${response.question?.field}, inputType=${response.question?.inputType}")
                    Log.d(TAG, "  hasConfirmationCard=${response.confirmationCard != null}, hasPlaceSearchParams=${response.placeSearchParams != null}")

                    // Sanitize response to handle edge cases safely
                    val sanitized = sanitizeResponse(response, stateForRequest.conversationId)

                    val assistantMessageUi = ChatMessageUi(
                        id = UUID.randomUUID().toString(),
                        content = sanitized.assistantMessage,
                        isUser = false
                    )

                    messageHistory.add(ChatMessage(role = "assistant", content = sanitized.assistantMessage))

                    // Merge extracted data into the latest slots (avoid stale merge base)
                    val latestSlots = _uiState.value.slots
                    val newSlots = mergeSlots(latestSlots, sanitized.extractedData)

                    _uiState.update {
                        it.copy(
                            messages = it.messages + assistantMessageUi,
                            slots = newSlots,
                            currentQuestion = sanitized.question,
                            confirmationCard = sanitized.confirmationCard,
                            nextAction = sanitized.nextAction,
                            isLoading = false,
                            isComplete = sanitized.isComplete,
                            placeSearchParams = sanitized.placeSearchParams
                        )
                    }
                },
                onFailure = { throwable ->
                    Log.e(TAG, "Backend error", throwable)
                    _uiState.update {
                        it.copy(
                            isLoading = false,
                            error = throwable.message ?: "Unknown error occurred"
                        )
                    }
                }
            )
        }
    }

    /**
     * Handle confirmation card response.
     * "Yes" sends "yes" to backend.
     * "Not quite" sends "no" to backend.
     */
    fun handleConfirmation(confirmed: Boolean) {
        val response = if (confirmed) "yes" else "no"
        sendMessage(response)
    }

    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * Handle "Continue" button after COMPLETE.
     * Triggers navigation to PlaceSearch screen using the placeSearchParams from backend.
     */
    fun handleContinue() {
        val params = _uiState.value.placeSearchParams
        if (params != null) {
            Log.i(TAG, "Continue clicked - navigating to PlaceSearch: query=${params.query}, area=${params.area}")
            _navigateToPlaceSearch.value = Pair(params.query, params.area)
        } else {
            Log.w(TAG, "Continue clicked but no placeSearchParams available")
        }
    }

    /**
     * Clear navigation event after handling.
     */
    fun clearNavigateToPlaceSearch() {
        _navigateToPlaceSearch.value = null
    }

    /**
     * Clear placeSearchParams after navigation to avoid re-navigation.
     */
    fun clearPlaceSearchParams() {
        _uiState.update { it.copy(placeSearchParams = null) }
    }

    /**
     * Merge new extracted data into existing slots.
     */
    private fun mergeSlots(existing: JsonObject, newData: JsonObject?): JsonObject {
        if (newData == null) return existing

        return buildJsonObject {
            existing.forEach { (key, value) -> put(key, value) }
            newData.forEach { (key, value) -> put(key, value) }
        }
    }

    /**
     * Sanitize and validate response from backend.
     * Ensures UI renders a safe model even if backend returns partial/invalid data.
     *
     * Edge cases handled:
     * - Empty assistantMessage -> fallback message
     * - Unknown nextAction -> treat as ASK_QUESTION
     * - FIND_PLACE without placeSearchParams -> show error
     * - ASK_QUESTION without question -> allow freeform input
     * - CONFIRM without confirmationCard -> treat as ASK_QUESTION
     *
     * @param conversationId For traceability in logs
     */
    private fun sanitizeResponse(
        response: ConversationResponse,
        conversationId: String
    ): SanitizedResponse {
        val sanitizationReasons = mutableListOf<String>()

        // Check assistantMessage
        val assistantMessage = if (response.assistantMessage.isBlank()) {
            sanitizationReasons.add("empty_assistant_message")
            "I'm not sure what to say. Please try again."
        } else {
            response.assistantMessage
        }

        // Validate nextAction combinations
        val (sanitizedAction, errorMessage) = when (response.nextAction) {
            NextAction.FIND_PLACE -> {
                if (response.placeSearchParams == null) {
                    sanitizationReasons.add("FIND_PLACE_missing_placeSearchParams")
                    NextAction.ASK_QUESTION to "I need more information before we can search for a place."
                } else {
                    response.nextAction to null
                }
            }
            NextAction.CONFIRM -> {
                if (response.confirmationCard == null) {
                    sanitizationReasons.add("CONFIRM_missing_confirmationCard")
                    NextAction.ASK_QUESTION to null
                } else {
                    response.nextAction to null
                }
            }
            NextAction.ASK_QUESTION -> {
                if (response.question == null) {
                    sanitizationReasons.add("ASK_QUESTION_missing_question")
                    // Don't change action - freeform input is acceptable
                }
                response.nextAction to null
            }
            else -> response.nextAction to null
        }

        // Log sanitization with conversationId for server-side correlation
        if (sanitizationReasons.isNotEmpty()) {
            Log.w(TAG, "Response sanitized [conversationId=$conversationId]: " +
                    "reasons=${sanitizationReasons.joinToString()}, " +
                    "originalAction=${response.nextAction}, " +
                    "sanitizedAction=$sanitizedAction")
        }

        return SanitizedResponse(
            assistantMessage = errorMessage ?: assistantMessage,
            nextAction = sanitizedAction,
            question = response.question,
            extractedData = response.extractedData,
            confirmationCard = if (sanitizedAction == NextAction.CONFIRM) response.confirmationCard else null,
            placeSearchParams = if (sanitizedAction == NextAction.FIND_PLACE) response.placeSearchParams else null,
            isComplete = sanitizedAction == NextAction.COMPLETE,
            wasSanitized = sanitizationReasons.isNotEmpty(),
            sanitizationReasons = sanitizationReasons
        )
    }

    /**
     * Sanitized response for UI rendering.
     */
    private data class SanitizedResponse(
        val assistantMessage: String,
        val nextAction: NextAction,
        val question: com.calleroo.app.domain.model.Question?,
        val extractedData: JsonObject?,
        val confirmationCard: com.calleroo.app.domain.model.ConfirmationCard?,
        val placeSearchParams: com.calleroo.app.domain.model.PlaceSearchParams?,
        val isComplete: Boolean,
        val wasSanitized: Boolean = false,
        val sanitizationReasons: List<String> = emptyList()
    )
}