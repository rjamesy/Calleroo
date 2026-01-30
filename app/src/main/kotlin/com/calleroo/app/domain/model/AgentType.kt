package com.calleroo.app.domain.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
enum class AgentType {
    @SerialName("STOCK_CHECKER")
    STOCK_CHECKER,

    @SerialName("RESTAURANT_RESERVATION")
    RESTAURANT_RESERVATION;

    val displayName: String
        get() = when (this) {
            STOCK_CHECKER -> "Stock Check"
            RESTAURANT_RESERVATION -> "Book Restaurant"
        }

    val description: String
        get() = when (this) {
            STOCK_CHECKER -> "Check product availability at retailers"
            RESTAURANT_RESERVATION -> "Book a table at a restaurant"
        }
}
