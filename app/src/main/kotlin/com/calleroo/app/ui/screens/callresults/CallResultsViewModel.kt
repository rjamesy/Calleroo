package com.calleroo.app.ui.screens.callresults

import android.util.Log
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calleroo.app.domain.model.CallResultFormatRequestV1
import com.calleroo.app.repository.CallBriefRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import javax.inject.Inject

@HiltViewModel
class CallResultsViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val repository: CallBriefRepository
) : ViewModel() {

    private val callId: String = checkNotNull(savedStateHandle["callId"]) {
        "callId is required"
    }

    private val agentType: String = checkNotNull(savedStateHandle["agentType"]) {
        "agentType is required"
    }

    private val _state = MutableStateFlow<CallResultsState>(CallResultsState.Loading())
    val state: StateFlow<CallResultsState> = _state.asStateFlow()

    companion object {
        private const val TAG = "CallResultsViewModel"
        private const val MAX_POLL_ATTEMPTS = 15  // Max 30 seconds polling
        private const val POLL_INTERVAL_MS = 2000L  // 2 seconds between polls
    }

    init {
        loadResults()
    }

    /**
     * Load call results by polling for transcript, then formatting.
     *
     * The transcript takes 10-20 seconds to process after a call completes
     * (recording download + Whisper transcription), so we poll until it's ready.
     */
    private fun loadResults() {
        viewModelScope.launch {
            _state.value = CallResultsState.Loading("Loading results...")

            // Poll until transcript is available or timeout
            var attempts = 0
            var lastResponse: com.calleroo.app.domain.model.CallStatusResponseV1? = null

            while (attempts < MAX_POLL_ATTEMPTS) {
                val statusResult = repository.getCallStatus(callId)

                val shouldBreak = statusResult.fold(
                    onSuccess = { response ->
                        lastResponse = response
                        Log.d(TAG, "Poll $attempts: status=${response.status}, transcript=${response.transcript?.take(50) ?: "null"}")

                        // Check if terminal and has transcript or outcome
                        if (response.isTerminal && (response.transcript != null || response.outcome != null)) {
                            Log.d(TAG, "Transcript ready after $attempts polls")
                            true // Break loop
                        } else if (response.isTerminal) {
                            // Terminal but no transcript yet - keep polling
                            attempts++
                            if (attempts < MAX_POLL_ATTEMPTS) {
                                _state.value = CallResultsState.Loading("Waiting for transcript... (${attempts}/${MAX_POLL_ATTEMPTS})")
                            }
                            false // Continue polling
                        } else {
                            // Not terminal - shouldn't happen from CallStatus nav
                            _state.value = CallResultsState.Error(
                                message = "Call is not finished yet (status: ${response.status})",
                                canRetry = true
                            )
                            true // Break loop (error case)
                        }
                    },
                    onFailure = { error ->
                        Log.e(TAG, "Failed to get call status", error)
                        _state.value = CallResultsState.Error(
                            message = "Failed to load call results: ${error.message}",
                            canRetry = true
                        )
                        true // Break loop (error case)
                    }
                )

                if (shouldBreak) break

                // Wait before next poll
                delay(POLL_INTERVAL_MS)
            }

            // Check if we hit an error state during polling
            if (_state.value is CallResultsState.Error) {
                return@launch
            }

            // Get the final response
            val response = lastResponse
            if (response == null) {
                _state.value = CallResultsState.Error(
                    message = "Failed to get call status after $MAX_POLL_ATTEMPTS attempts",
                    canRetry = true
                )
                return@launch
            }

            // If we timed out without transcript, proceed with what we have
            if (response.transcript == null && response.outcome == null) {
                Log.w(TAG, "Timeout waiting for transcript, proceeding with fallback")
            }

            // Format the results using the backend service
            formatAndDisplayResults(response)
        }
    }

    /**
     * Format the call results and update state.
     */
    private suspend fun formatAndDisplayResults(response: com.calleroo.app.domain.model.CallStatusResponseV1) {
        val formatRequest = CallResultFormatRequestV1(
            agentType = agentType,
            callId = callId,
            status = response.status,
            durationSeconds = response.durationSeconds,
            transcript = response.transcript,
            outcome = response.outcome,
            error = response.error
        )

        val formatResult = repository.formatCallResult(formatRequest)

        formatResult.fold(
            onSuccess = { formatted ->
                Log.d(TAG, "Formatted results: ${formatted.title}")
                _state.value = CallResultsState.Ready(
                    title = formatted.title,
                    status = response.status,
                    durationSeconds = response.durationSeconds,
                    bullets = formatted.bullets,
                    extractedFacts = formatted.extractedFacts,
                    nextSteps = formatted.nextSteps,
                    transcript = formatted.formattedTranscript ?: response.transcript,
                    rawOutcome = response.outcome,
                    error = response.error
                )
            },
            onFailure = { error ->
                Log.e(TAG, "Failed to format results", error)
                // Fallback: show basic results without formatting
                _state.value = CallResultsState.Ready(
                    title = getTitleForStatus(response.status),
                    status = response.status,
                    durationSeconds = response.durationSeconds,
                    bullets = buildFallbackBullets(response.status, response.durationSeconds, response.error),
                    extractedFacts = JsonObject(emptyMap()),
                    nextSteps = buildFallbackNextSteps(response.status),
                    transcript = response.transcript,
                    rawOutcome = response.outcome,
                    error = response.error
                )
            }
        )
    }

    /**
     * Retry loading results.
     */
    fun retry() {
        loadResults()
    }

    // Fallback helpers when formatting fails

    private fun getTitleForStatus(status: String): String = when (status) {
        "completed" -> "Call completed"
        "failed" -> "Call failed"
        "busy" -> "Line was busy"
        "no-answer" -> "No answer"
        "canceled" -> "Call canceled"
        else -> "Call ended"
    }

    private fun buildFallbackBullets(status: String, durationSeconds: Int?, error: String?): List<String> {
        val bullets = mutableListOf<String>()

        if (durationSeconds != null) {
            val minutes = durationSeconds / 60
            val seconds = durationSeconds % 60
            bullets.add(if (minutes > 0) "Duration: ${minutes}m ${seconds}s" else "Duration: ${seconds}s")
        }

        if (error != null) {
            bullets.add("Error: $error")
        }

        when (status) {
            "completed" -> bullets.add("Call completed successfully")
            "busy" -> bullets.add("The recipient's line was busy")
            "no-answer" -> bullets.add("The call was not answered")
            "failed" -> bullets.add("The call could not be connected")
            "canceled" -> bullets.add("The call was canceled")
        }

        return bullets
    }

    private fun buildFallbackNextSteps(status: String): List<String> {
        val steps = mutableListOf<String>()

        if (status in listOf("failed", "busy", "no-answer")) {
            steps.add("Try calling again later")
        }

        if (status == "completed") {
            steps.add("Review the call details")
        }

        steps.add("Start a new call")

        return steps
    }
}
