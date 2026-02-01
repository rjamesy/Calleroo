package com.calleroo.app.ui.screens.scheduledtasks

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calleroo.app.domain.model.AgentType
import com.calleroo.app.domain.model.ScheduledTaskDto
import com.calleroo.app.domain.model.ScheduledTaskUiModel
import com.calleroo.app.domain.model.TaskStatus
import com.calleroo.app.repository.SchedulerRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException
import javax.inject.Inject

@HiltViewModel
class ScheduledTasksViewModel @Inject constructor(
    private val schedulerRepository: SchedulerRepository
) : ViewModel() {

    private val _state = MutableStateFlow<ScheduledTasksState>(ScheduledTasksState.Loading)
    val state: StateFlow<ScheduledTasksState> = _state.asStateFlow()

    companion object {
        private const val TAG = "ScheduledTasksViewModel"
    }

    init {
        loadTasks()
    }

    private fun loadTasks(filter: StatusFilter = StatusFilter.ALL, isRefresh: Boolean = false) {
        viewModelScope.launch {
            // Check if scheduler is available
            if (!schedulerRepository.isAvailable) {
                _state.value = ScheduledTasksState.Disabled
                return@launch
            }

            // Set loading or refreshing state
            if (!isRefresh) {
                _state.value = ScheduledTasksState.Loading
            } else {
                val currentState = _state.value
                if (currentState is ScheduledTasksState.Ready) {
                    _state.value = currentState.copy(isRefreshing = true)
                }
            }

            val result = schedulerRepository.listTasks(status = filter.apiValue)

            result.fold(
                onSuccess = { tasks ->
                    Log.d(TAG, "Loaded ${tasks.size} tasks")
                    val uiModels = tasks.map { it.toUiModel() }
                    _state.value = ScheduledTasksState.Ready(
                        tasks = uiModels,
                        selectedFilter = filter,
                        isRefreshing = false
                    )
                },
                onFailure = { error ->
                    Log.e(TAG, "Failed to load tasks", error)
                    _state.value = ScheduledTasksState.Error(
                        message = error.message ?: "Failed to load scheduled tasks"
                    )
                }
            )
        }
    }

    /**
     * Refresh the task list (pull-to-refresh).
     */
    fun refresh() {
        val currentFilter = (_state.value as? ScheduledTasksState.Ready)?.selectedFilter
            ?: StatusFilter.ALL
        loadTasks(filter = currentFilter, isRefresh = true)
    }

    /**
     * Change the status filter.
     */
    fun setFilter(filter: StatusFilter) {
        loadTasks(filter = filter, isRefresh = false)
    }

    /**
     * Retry loading after error.
     */
    fun retry() {
        loadTasks()
    }

    /**
     * Convert DTO to UI model with formatted display values.
     */
    private fun ScheduledTaskDto.toUiModel(): ScheduledTaskUiModel {
        // Parse agent type for display name
        val agentLabel = try {
            AgentType.valueOf(agentType).displayName
        } catch (e: IllegalArgumentException) {
            agentType
        }

        // Format run time in local timezone
        val runAtLocalFormatted = formatUtcToLocal(runAtUtc)

        // Map status to TaskStatus enum
        val taskStatus = TaskStatus.fromValue(status) ?: TaskStatus.SCHEDULED

        // Status label with proper casing
        val statusLabel = when (taskStatus) {
            TaskStatus.SCHEDULED -> "Scheduled"
            TaskStatus.RUNNING -> "Running"
            TaskStatus.COMPLETED -> "Completed"
            TaskStatus.FAILED -> "Failed"
            TaskStatus.CANCELED -> "Canceled"
        }

        // Subtitle line: use placeId fallback to conversationId
        val subtitleLine = if (!placeId.isNullOrBlank()) {
            "Place: ${placeId.take(20)}..."
        } else {
            "ID: ${conversationId.take(8)}..."
        }

        return ScheduledTaskUiModel(
            taskId = taskId,
            agentLabel = agentLabel,
            runAtLocalFormatted = runAtLocalFormatted,
            statusLabel = statusLabel,
            status = taskStatus,
            subtitleLine = subtitleLine
        )
    }

    /**
     * Format a UTC ISO 8601 timestamp to local time display.
     */
    private fun formatUtcToLocal(utcTimestamp: String): String {
        return try {
            val zonedDateTime = ZonedDateTime.parse(utcTimestamp)
            val localDateTime = zonedDateTime.withZoneSameInstant(ZoneId.systemDefault())
            val formatter = DateTimeFormatter.ofPattern("MMM d, h:mm a")
            localDateTime.format(formatter)
        } catch (e: DateTimeParseException) {
            Log.w(TAG, "Failed to parse timestamp: $utcTimestamp", e)
            utcTimestamp
        }
    }
}
