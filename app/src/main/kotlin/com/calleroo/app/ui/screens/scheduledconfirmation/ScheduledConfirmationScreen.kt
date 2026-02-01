package com.calleroo.app.ui.screens.scheduledconfirmation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.calleroo.app.domain.model.AgentType
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.ZoneId

/**
 * Confirmation screen shown after successfully scheduling a call.
 *
 * Displays the agent type and scheduled time, with a "Continue" button
 * that returns to the home screen.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ScheduledConfirmationScreen(
    agentType: String,
    scheduledTimeUtc: String,
    onNavigateToHome: () -> Unit
) {
    val agentLabel = getAgentFriendlyLabel(agentType)
    val formattedTime = formatScheduledTime(scheduledTimeUtc)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Call Scheduled") }
            )
        },
        bottomBar = {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                tonalElevation = 3.dp,
                shadowElevation = 8.dp
            ) {
                Button(
                    onClick = onNavigateToHome,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                ) {
                    Text("Continue")
                }
            }
        }
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentAlignment = Alignment.Center
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(24.dp),
                modifier = Modifier.padding(32.dp)
            ) {
                // Success icon
                Box(
                    modifier = Modifier
                        .size(100.dp)
                        .background(
                            color = MaterialTheme.colorScheme.primaryContainer,
                            shape = CircleShape
                        ),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(
                        imageVector = Icons.Default.Schedule,
                        contentDescription = "Scheduled",
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(48.dp)
                    )
                }

                // Title
                Text(
                    text = "Your call has been scheduled!",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center
                )

                // Agent type
                Text(
                    text = agentLabel,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary
                )

                // Scheduled time card
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = "Scheduled for",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = formattedTime,
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Medium
                        )
                    }
                }

                // Info text
                Text(
                    text = "We'll make the call at the scheduled time. You'll receive a notification when the call completes.",
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Center,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Convert agent type enum name to user-friendly label.
 */
private fun getAgentFriendlyLabel(agentType: String): String {
    return try {
        AgentType.valueOf(agentType).displayName
    } catch (e: IllegalArgumentException) {
        // Fallback: convert SNAKE_CASE to Title Case
        agentType.replace("_", " ")
            .lowercase()
            .replaceFirstChar { it.uppercase() }
    }
}

/**
 * Format UTC timestamp to local time for display.
 */
private fun formatScheduledTime(utcTimestamp: String): String {
    return try {
        // Decode URL-encoded timestamp
        val decoded = URLDecoder.decode(utcTimestamp, StandardCharsets.UTF_8.toString())
        val zonedDateTime = ZonedDateTime.parse(decoded)
        val localDateTime = zonedDateTime.withZoneSameInstant(ZoneId.systemDefault())
        val formatter = DateTimeFormatter.ofPattern("EEE, MMM d 'at' h:mm a")
        localDateTime.format(formatter)
    } catch (e: Exception) {
        // Fallback to raw string
        utcTimestamp
    }
}
