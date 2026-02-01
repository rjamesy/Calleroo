package com.calleroo.app.domain.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Payload for DIRECT mode task creation.
 * Contains all data needed to call /call/start directly.
 */
@Serializable
data class DirectTaskPayload(
    val placeId: String,
    val phoneE164: String,
    val scriptPreview: String,
    val slots: JsonObject
)

/**
 * Request body for POST /tasks endpoint on the scheduler service.
 */
@Serializable
data class CreateScheduledTaskRequest(
    val runAtUtc: String,           // ISO 8601 UTC timestamp (e.g., "2026-02-01T22:00:00Z")
    val backendBaseUrl: String,     // Backend API base URL
    val agentType: String,          // e.g., "STOCK_CHECKER", "CANCEL_APPOINTMENT"
    val conversationId: String,
    val mode: String = "DIRECT",    // "DIRECT" or "BRIEF_START"
    val payload: DirectTaskPayload,
    val timezone: String? = null    // Original timezone for reference
)

/**
 * Response from POST /tasks endpoint.
 */
@Serializable
data class CreateScheduledTaskResponse(
    val taskId: String,
    val status: String  // "SCHEDULED"
)

// ============================================================================
// GET /tasks response models
// ============================================================================

/**
 * Task status enum matching the scheduler service.
 */
enum class TaskStatus(val value: String) {
    SCHEDULED("SCHEDULED"),
    RUNNING("RUNNING"),
    COMPLETED("COMPLETED"),
    FAILED("FAILED"),
    CANCELED("CANCELED");

    companion object {
        fun fromValue(value: String): TaskStatus? =
            entries.find { it.value.equals(value, ignoreCase = true) }
    }
}

/**
 * Event log entry for a scheduled task.
 */
@Serializable
data class TaskEventDto(
    val id: Int,
    val tsUtc: String,
    val level: String,  // "INFO", "WARN", "ERROR"
    val message: String
)

/**
 * Full task object returned by GET /tasks and GET /tasks/{taskId}.
 */
@Serializable
data class ScheduledTaskDto(
    val taskId: String,
    val status: String,
    val runAtUtc: String,
    val agentType: String,
    val conversationId: String,
    val mode: String,
    val placeId: String? = null,
    val phoneE164: String? = null,
    val callId: String? = null,
    val lastError: String? = null,
    val createdAt: String,
    val updatedAt: String,
    val events: List<TaskEventDto> = emptyList()
)

// ============================================================================
// UI models for ScheduledTasks screen
// ============================================================================

/**
 * UI model for displaying a scheduled task in a list.
 */
data class ScheduledTaskUiModel(
    val taskId: String,
    val agentLabel: String,
    val runAtLocalFormatted: String,
    val statusLabel: String,
    val status: TaskStatus,
    val subtitleLine: String
)
