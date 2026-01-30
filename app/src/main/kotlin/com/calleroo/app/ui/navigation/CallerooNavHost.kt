package com.calleroo.app.ui.navigation

import android.util.Log
import androidx.compose.runtime.Composable
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.calleroo.app.domain.model.AgentType
import com.calleroo.app.ui.screens.agentselect.AgentSelectScreen
import com.calleroo.app.ui.screens.chat.UnifiedChatScreen
import com.calleroo.app.ui.screens.placesearch.PlaceSearchScreen

private const val TAG = "CallerooNavHost"

@Composable
fun CallerooNavHost() {
    val navController = rememberNavController()

    NavHost(
        navController = navController,
        startDestination = NavRoutes.AgentSelect.route
    ) {
        // Screen 1: Agent Selection
        composable(route = NavRoutes.AgentSelect.route) {
            AgentSelectScreen(
                onAgentSelected = { agentType, conversationId ->
                    navController.navigate(
                        NavRoutes.Chat.createRoute(agentType, conversationId)
                    )
                }
            )
        }

        // Screen 2: Unified Chat
        composable(
            route = NavRoutes.Chat.route,
            arguments = listOf(
                navArgument("agentType") { type = NavType.StringType },
                navArgument("conversationId") { type = NavType.StringType }
            )
        ) { backStackEntry ->
            val agentTypeName = backStackEntry.arguments?.getString("agentType") ?: ""
            val conversationId = backStackEntry.arguments?.getString("conversationId") ?: ""
            val agentType = AgentType.valueOf(agentTypeName)

            UnifiedChatScreen(
                agentType = agentType,
                conversationId = conversationId,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToPlaceSearch = { query, area ->
                    navController.navigate(
                        NavRoutes.PlaceSearch.createRoute(agentType, query, area)
                    )
                }
            )
        }

        // Screen 3: Place Search
        composable(
            route = NavRoutes.PlaceSearch.route,
            arguments = listOf(
                navArgument("agentType") { type = NavType.StringType },
                navArgument("query") { type = NavType.StringType },
                navArgument("area") { type = NavType.StringType }
            )
        ) { _ ->
            // Note: query and area are URL-decoded in the ViewModel via SavedStateHandle

            PlaceSearchScreen(
                onNavigateBack = { navController.popBackStack() },
                onPlaceResolved = { resolvedState ->
                    // TODO: Navigate to Screen 4 (Call Summary) with resolved place data
                    // For now, just log and pop back - Step 2 stops here
                    Log.i(TAG, "NEXT_SCREEN_NOT_IMPLEMENTED: Place resolved - " +
                            "name=${resolvedState.businessName}, " +
                            "phone=${resolvedState.phoneE164}")
                    navController.popBackStack()
                }
            )
        }
    }
}
