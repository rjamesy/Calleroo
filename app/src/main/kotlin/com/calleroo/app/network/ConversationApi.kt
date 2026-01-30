package com.calleroo.app.network

import com.calleroo.app.domain.model.ConversationRequest
import com.calleroo.app.domain.model.ConversationResponse
import com.calleroo.app.domain.model.PlaceDetailsRequest
import com.calleroo.app.domain.model.PlaceDetailsResponse
import com.calleroo.app.domain.model.PlaceSearchRequest
import com.calleroo.app.domain.model.PlaceSearchResponse
import retrofit2.http.Body
import retrofit2.http.POST

interface ConversationApi {

    @POST("/conversation/next")
    suspend fun nextTurn(@Body request: ConversationRequest): ConversationResponse

    @POST("/places/search")
    suspend fun placesSearch(@Body request: PlaceSearchRequest): PlaceSearchResponse

    @POST("/places/details")
    suspend fun placesDetails(@Body request: PlaceDetailsRequest): PlaceDetailsResponse
}
