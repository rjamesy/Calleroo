package com.calleroo.app.ui.screens.scheduledtasks

import com.calleroo.app.domain.model.ScheduledTaskUiModel

/**
 * State for the Scheduled Tasks screen.
 *
 * This screen shows a read-only list of scheduled tasks from the scheduler service.
 */
sealed class ScheduledTasksState {

    /**
     * Loading state - fetching tasks from scheduler.
     */
    data object Loading : ScheduledTasksState()

    /**
     * Scheduler is disabled (SCHEDULER_BASE_URL not configured).
     */
    data object Disabled : ScheduledTasksState()

    /**
     * Error state - something went wrong fetching tasks.
     */
    data class Error(
        val message: String
    ) : ScheduledTasksState()

    /**
     * Ready state - tasks loaded successfully.
     */
    data class Ready(
        val tasks: List<ScheduledTaskUiModel>,
        val selectedFilter: StatusFilter,
        val isRefreshing: Boolean = false
    ) : ScheduledTasksState() {
        val isEmpty: Boolean
            get() = tasks.isEmpty()
    }
}

/**
 * Filter options for the task list.
 */
enum class StatusFilter(val label: String, val apiValue: String?) {
    ALL("All", null),
    SCHEDULED("Scheduled", "SCHEDULED"),
    COMPLETED("Completed", "COMPLETED"),
    FAILED("Failed", "FAILED")
}
