package com.calleroo.app.ui.screens.callresults

import kotlinx.serialization.json.JsonObject

/**
 * State for the Call Results screen.
 *
 * This screen is shown after a call terminates (completed, failed, busy, no-answer, canceled).
 * It displays a formatted summary of the call results.
 */
sealed class CallResultsState {

    /**
     * Loading state - fetching call status and formatting results.
     * Message updates as we poll for transcript.
     */
    data class Loading(
        val message: String = "Loading results..."
    ) : CallResultsState()

    /**
     * Results ready for display.
     */
    data class Ready(
        val title: String,
        val status: String,
        val durationSeconds: Int?,
        val bullets: List<String>,
        val extractedFacts: JsonObject,
        val nextSteps: List<String>,
        val transcript: String?, // formattedTranscript if available, else raw
        val rawOutcome: JsonObject?,
        val error: String?
    ) : CallResultsState() {
        /**
         * Formatted duration string.
         */
        val formattedDuration: String?
            get() {
                if (durationSeconds == null) return null
                val minutes = durationSeconds / 60
                val seconds = durationSeconds % 60
                return if (minutes > 0) {
                    "${minutes}m ${seconds}s"
                } else {
                    "${seconds}s"
                }
            }

        /**
         * Status chip color indicator.
         */
        val isSuccess: Boolean
            get() = status == "completed" && error == null
    }

    /**
     * Error state - something went wrong.
     */
    data class Error(
        val message: String,
        val canRetry: Boolean = true
    ) : CallResultsState()
}
