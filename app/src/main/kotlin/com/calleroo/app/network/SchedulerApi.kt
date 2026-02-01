package com.calleroo.app.network

import com.calleroo.app.domain.model.CreateScheduledTaskRequest
import com.calleroo.app.domain.model.CreateScheduledTaskResponse
import com.calleroo.app.domain.model.ScheduledTaskDto
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * Retrofit interface for the Calleroo Scheduler Service.
 *
 * The scheduler service is separate from the main backend and handles
 * scheduling calls for future execution.
 */
interface SchedulerApi {

    /**
     * Create a new scheduled task.
     *
     * @param request Task creation request with schedule time and call details
     * @return Response containing taskId and status
     */
    @POST("/tasks")
    suspend fun createTask(@Body request: CreateScheduledTaskRequest): CreateScheduledTaskResponse

    /**
     * List scheduled tasks with optional status filter.
     *
     * @param status Optional filter: SCHEDULED, RUNNING, COMPLETED, FAILED, CANCELED
     * @param limit Max number of results (default 50)
     * @return List of scheduled tasks
     */
    @GET("/tasks")
    suspend fun listTasks(
        @Query("status") status: String? = null,
        @Query("limit") limit: Int? = null
    ): List<ScheduledTaskDto>
}
