package com.calleroo.app.ui.navigation

import com.calleroo.app.domain.model.AgentType
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

sealed class NavRoutes(val route: String) {
    data object AgentSelect : NavRoutes("agent_select")

    data object Chat : NavRoutes("chat/{agentType}/{conversationId}") {
        fun createRoute(agentType: AgentType, conversationId: String): String {
            return "chat/${agentType.name}/$conversationId"
        }
    }

    data object PlaceSearch : NavRoutes("place_search/{agentType}/{query}/{area}") {
        fun createRoute(agentType: AgentType, query: String, area: String): String {
            val encodedQuery = URLEncoder.encode(query, StandardCharsets.UTF_8.toString())
            val encodedArea = URLEncoder.encode(area, StandardCharsets.UTF_8.toString())
            return "place_search/${agentType.name}/$encodedQuery/$encodedArea"
        }
    }
}
