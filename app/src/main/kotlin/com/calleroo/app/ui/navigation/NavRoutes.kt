package com.calleroo.app.ui.navigation

import com.calleroo.app.domain.model.AgentType
import java.net.URLDecoder
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

sealed class NavRoutes(val route: String) {
    data object AgentSelect : NavRoutes("agent_select")

    /**
     * Screen: Scheduled Tasks - read-only list of scheduled tasks.
     */
    data object ScheduledTasks : NavRoutes("scheduled_tasks")

    /**
     * Nested navigation graph for task flow (Screens 2-4).
     * TaskSessionViewModel is scoped to this graph for shared state.
     */
    data object TaskFlowGraph : NavRoutes("task_flow/{agentType}/{conversationId}") {
        fun createRoute(agentType: AgentType, conversationId: String): String {
            return "task_flow/${agentType.name}/$conversationId"
        }
    }

    /**
     * Screen 2: Chat - conversation with the assistant.
     * This is the start destination within TaskFlowGraph.
     */
    data object Chat : NavRoutes("chat")

    /**
     * Screen 3: Place Search - find and select a business to call.
     */
    data object PlaceSearch : NavRoutes("place_search/{query}/{area}") {
        // Collision-proof sentinel for empty values (user won't type this)
        private const val EMPTY_SENTINEL = "__CALLEROO_EMPTY__"

        fun createRoute(query: String, area: String): String {
            // Defensive: ensure non-empty strings for navigation to prevent crash
            val safeQuery = query.ifBlank { EMPTY_SENTINEL }
            val safeArea = area.ifBlank { EMPTY_SENTINEL }
            val encodedQuery = URLEncoder.encode(safeQuery, StandardCharsets.UTF_8.toString())
            val encodedArea = URLEncoder.encode(safeArea, StandardCharsets.UTF_8.toString())
            return "place_search/$encodedQuery/$encodedArea"
        }

        fun decodeParam(encoded: String): String {
            val decoded = URLDecoder.decode(encoded, StandardCharsets.UTF_8.toString())
            return if (decoded == EMPTY_SENTINEL) "" else decoded
        }
    }

    /**
     * Screen 4: Call Summary - review call brief before starting the call.
     */
    data object CallSummary : NavRoutes("call_summary")

    /**
     * Screen 5: Call Status - monitor active call and show results.
     * Now includes agentType for navigation to CallResults.
     */
    data object CallStatus : NavRoutes("call_status/{callId}/{agentType}") {
        fun createRoute(callId: String, agentType: String): String {
            return "call_status/$callId/$agentType"
        }
    }

    /**
     * Screen 6: Call Results - display formatted call results after terminal status.
     */
    data object CallResults : NavRoutes("call_results/{callId}/{agentType}") {
        fun createRoute(callId: String, agentType: String): String {
            return "call_results/$callId/$agentType"
        }
    }

    /**
     * Screen: Scheduled Confirmation - shows details after successfully scheduling a call.
     */
    data object ScheduledConfirmation : NavRoutes("scheduled_confirmation/{agentType}/{scheduledTimeUtc}") {
        fun createRoute(agentType: String, scheduledTimeUtc: String): String {
            val encodedTime = URLEncoder.encode(scheduledTimeUtc, StandardCharsets.UTF_8.toString())
            return "scheduled_confirmation/$agentType/$encodedTime"
        }
    }
}
