package com.calleroo.app.repository

import com.calleroo.app.domain.model.CreateScheduledTaskRequest
import com.calleroo.app.domain.model.CreateScheduledTaskResponse
import com.calleroo.app.domain.model.ScheduledTaskDto
import com.calleroo.app.network.SchedulerApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for interacting with the Calleroo Scheduler Service.
 *
 * This repository wraps the SchedulerApi and provides error handling.
 * If the scheduler URL is not configured, the API will be null and
 * [isAvailable] will return false.
 */
@Singleton
class SchedulerRepository @Inject constructor(
    private val schedulerApi: SchedulerApi?  // Nullable when URL not configured
) {

    /**
     * Check if the scheduler service is available (URL configured).
     */
    val isAvailable: Boolean
        get() = schedulerApi != null

    /**
     * Create a new scheduled task.
     *
     * @param request The task creation request with schedule time and call details
     * @return Result containing the task response or an error
     */
    suspend fun createTask(request: CreateScheduledTaskRequest): Result<CreateScheduledTaskResponse> {
        val api = schedulerApi ?: return Result.failure(
            IllegalStateException("Scheduler service not configured")
        )

        return try {
            val response = api.createTask(request)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * List scheduled tasks with optional status filter.
     *
     * @param status Optional filter by status (SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELED)
     * @return Result containing list of tasks or an error
     */
    suspend fun listTasks(status: String? = null): Result<List<ScheduledTaskDto>> {
        val api = schedulerApi ?: return Result.failure(
            IllegalStateException("Scheduler service not configured")
        )

        return try {
            val response = api.listTasks(status = status)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
