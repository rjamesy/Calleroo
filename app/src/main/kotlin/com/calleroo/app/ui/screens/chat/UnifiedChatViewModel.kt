package com.calleroo.app.ui.screens.chat

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calleroo.app.domain.model.AgentType
import com.calleroo.app.domain.model.ChatMessage
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
import kotlinx.serialization.json.jsonObject
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class UnifiedChatViewModel @Inject constructor(
    private val conversationRepository: ConversationRepository
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private var messageHistory: MutableList<ChatMessage> = mutableListOf()

    companion object {
        private const val TAG = "UnifiedChatViewModel"
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

        // Start conversation by sending empty message to get first question
        sendMessage("")
    }

    /**
     * Send a user message to the backend.
     *
     * CRITICAL: This method does NO local logic.
     * It ONLY posts to /conversation/next and renders the response.
     */
    fun sendMessage(userMessage: String) {
        val currentState = _uiState.value

        // Add user message to UI (if not empty/initial)
        if (userMessage.isNotBlank()) {
            val userMessageUi = ChatMessageUi(
                id = UUID.randomUUID().toString(),
                content = userMessage,
                isUser = true
            )
            _uiState.update { it.copy(messages = it.messages + userMessageUi) }

            // Add to history for backend
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
            val result = conversationRepository.nextTurn(
                conversationId = currentState.conversationId,
                agentType = currentState.agentType,
                userMessage = userMessage,
                slots = currentState.slots,
                messageHistory = messageHistory.toList(),
                debug = true
            )

            result.fold(
                onSuccess = { response ->
                    // CRITICAL: Verify backend drove this response
                    UnifiedConversationGuard.assertBackendDriven(response.aiCallMade)

                    Log.d(TAG, "Backend response: action=${response.nextAction}, aiModel=${response.aiModel}")

                    // Add assistant message to UI
                    val assistantMessageUi = ChatMessageUi(
                        id = UUID.randomUUID().toString(),
                        content = response.assistantMessage,
                        isUser = false
                    )

                    // Add to history for backend
                    messageHistory.add(ChatMessage(role = "assistant", content = response.assistantMessage))

                    // Merge extracted data into slots
                    val newSlots = mergeSlots(currentState.slots, response.extractedData)

                    _uiState.update {
                        it.copy(
                            messages = it.messages + assistantMessageUi,
                            slots = newSlots,
                            currentQuestion = response.question,
                            confirmationCard = response.confirmationCard,
                            nextAction = response.nextAction,
                            isLoading = false,
                            isComplete = response.nextAction == NextAction.COMPLETE,
                            placeSearchParams = response.placeSearchParams
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

    /**
     * Clear error state.
     */
    fun clearError() {
        _uiState.update { it.copy(error = null) }
    }

    /**
     * Handle "Continue" button after COMPLETE.
     * Step 1: Just logs that next screen is not implemented.
     */
    fun handleContinue() {
        Log.i(TAG, "NEXT_SCREEN_NOT_IMPLEMENTED")
    }

    /**
     * Clear placeSearchParams after navigation to avoid re-navigation.
     */
    fun clearPlaceSearchParams() {
        _uiState.update { it.copy(placeSearchParams = null) }
    }

    /**
     * Merge new extracted data into existing slots.
     * Server-side merging is authoritative, but we also track locally for display.
     */
    private fun mergeSlots(existing: JsonObject, newData: JsonObject?): JsonObject {
        if (newData == null) return existing

        return buildJsonObject {
            // Copy existing slots
            existing.forEach { (key, value) ->
                put(key, value)
            }
            // Add/override with new data
            newData.forEach { (key, value) ->
                put(key, value)
            }
        }
    }
}
