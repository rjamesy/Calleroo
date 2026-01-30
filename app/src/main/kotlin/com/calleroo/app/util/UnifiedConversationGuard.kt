package com.calleroo.app.util

import com.calleroo.app.BuildConfig

/**
 * Runtime guard that prevents any local conversation logic from running in debug builds.
 *
 * CRITICAL: The Android client MUST NOT decide questions, slots, flow order, or "what to ask next".
 * The backend (OpenAI) is the sole authority for all conversation flow.
 *
 * In debug builds, if any legacy/local logic is invoked, this guard throws a RuntimeException.
 * This ensures we catch any accidental local logic during development.
 */
object UnifiedConversationGuard {

    private const val ERROR_MESSAGE = "LOCAL_LOGIC_FORBIDDEN: " +
            "The Android client must not implement local question order, slot inference, or fallbacks. " +
            "All conversation logic must come from the backend."

    /**
     * Call this method at any point where local conversation logic WOULD have been invoked.
     * In debug builds, this crashes the app to alert developers.
     * In release builds, this is a no-op (but should never be reached if code is clean).
     */
    fun assertNoLocalLogic(context: String = "") {
        if (BuildConfig.ENABLE_LOCAL_LOGIC_GUARD) {
            val message = if (context.isNotEmpty()) {
                "$ERROR_MESSAGE\nContext: $context"
            } else {
                ERROR_MESSAGE
            }
            throw RuntimeException(message)
        }
    }

    /**
     * Validates that a response came from the backend (aiCallMade == true).
     * Crashes in debug builds if the response doesn't have aiCallMade flag.
     */
    fun assertBackendDriven(aiCallMade: Boolean) {
        if (BuildConfig.ENABLE_LOCAL_LOGIC_GUARD && !aiCallMade) {
            throw RuntimeException(
                "LOCAL_LOGIC_FORBIDDEN: Response did not come from AI backend. " +
                        "aiCallMade must be true for all responses."
            )
        }
    }

    /**
     * Validates that choices are only rendered when the backend sends them.
     * Call this before rendering any choice chips.
     */
    fun assertChoicesFromBackend(choices: List<Any>?, backendProvided: Boolean) {
        if (BuildConfig.ENABLE_LOCAL_LOGIC_GUARD) {
            if (choices != null && choices.isNotEmpty() && !backendProvided) {
                throw RuntimeException(
                    "LOCAL_LOGIC_FORBIDDEN: Choice chips must only be rendered when " +
                            "backend sends them. Local chip generation is forbidden."
                )
            }
        }
    }
}
