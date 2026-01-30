package com.calleroo.app.repository

import com.calleroo.app.domain.model.PlaceDetailsRequest
import com.calleroo.app.domain.model.PlaceDetailsResponse
import com.calleroo.app.domain.model.PlaceSearchRequest
import com.calleroo.app.domain.model.PlaceSearchResponse
import com.calleroo.app.network.ConversationApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Repository for Place Search operations.
 *
 * This repository does NO local logic - it just passes data through.
 * All place search logic is handled by the backend.
 * NO OpenAI calls are made from these endpoints.
 */
@Singleton
class PlacesRepository @Inject constructor(
    private val conversationApi: ConversationApi
) {
    /**
     * Search for places matching the query in the specified area.
     *
     * @param query Search query (e.g., "JB Hi-Fi" or "Thai Palace restaurant")
     * @param area Area to search in (e.g., "Browns Plains" or "Richmond VIC")
     * @param radiusKm Search radius in kilometers (25, 50, or 100)
     */
    suspend fun searchPlaces(
        query: String,
        area: String,
        radiusKm: Int = 25
    ): Result<PlaceSearchResponse> {
        return try {
            val request = PlaceSearchRequest(
                query = query,
                area = area,
                radiusKm = radiusKm
            )
            val response = conversationApi.placesSearch(request)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Get detailed information about a specific place.
     *
     * @param placeId Google Place ID
     */
    suspend fun getPlaceDetails(placeId: String): Result<PlaceDetailsResponse> {
        return try {
            val request = PlaceDetailsRequest(placeId = placeId)
            val response = conversationApi.placesDetails(request)
            Result.success(response)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
