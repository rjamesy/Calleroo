package com.calleroo.app.ui.screens.placesearch

import android.util.Log
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.calleroo.app.BuildConfig
import com.calleroo.app.domain.model.PlaceCandidate
import com.calleroo.app.repository.PlacesRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import javax.inject.Inject

/**
 * ViewModel for Place Search screen (Screen 3).
 *
 * Manages the state machine for place search:
 * - Initial search with 25km radius
 * - Radius expansion (25 -> 50 -> 100km) on user request
 * - Place selection and detail fetching
 * - Phone number validation (E.164 required)
 *
 * NO local "smart" logic - all data comes from backend.
 * NO GPS/location - uses area string from chat.
 */
@HiltViewModel
class PlaceSearchViewModel @Inject constructor(
    private val placesRepository: PlacesRepository,
    savedStateHandle: SavedStateHandle
) : ViewModel() {

    private val _state = MutableStateFlow<PlaceSearchState>(PlaceSearchState.Loading())
    val state: StateFlow<PlaceSearchState> = _state.asStateFlow()

    // Navigation arguments (URL decoded)
    val query: String = URLDecoder.decode(
        savedStateHandle.get<String>("query") ?: "",
        StandardCharsets.UTF_8.toString()
    )
    val area: String = URLDecoder.decode(
        savedStateHandle.get<String>("area") ?: "",
        StandardCharsets.UTF_8.toString()
    )

    // Track current radius for UI and expansion logic
    private var currentRadiusKm: Int = INITIAL_RADIUS_KM

    // Keep last results for returning from error state
    private var lastResults: PlaceSearchState.Results? = null

    companion object {
        private const val TAG = "PlaceSearchViewModel"
        private const val INITIAL_RADIUS_KM = 25
        private const val EXPANDED_RADIUS_KM = 50
        private const val MAX_RADIUS_KM = 100
    }

    init {
        // Start search immediately
        if (query.isNotBlank() && area.isNotBlank()) {
            searchPlaces(INITIAL_RADIUS_KM)
        } else {
            Log.e(TAG, "Missing search parameters: query='$query', area='$area'")
            _state.value = PlaceSearchState.Error("Missing search parameters")
        }
    }

    /**
     * Search for places at the specified radius.
     */
    fun searchPlaces(radiusKm: Int = currentRadiusKm) {
        currentRadiusKm = radiusKm
        _state.value = PlaceSearchState.Loading(
            radiusKm = radiusKm,
            message = "Searching within ${radiusKm}km..."
        )

        viewModelScope.launch {
            Log.d(TAG, "Searching: query='$query', area='$area', radius=${radiusKm}km")

            val result = placesRepository.searchPlaces(
                query = query,
                area = area,
                radiusKm = radiusKm
            )

            result.fold(
                onSuccess = { response ->
                    Log.d(TAG, "Search success: ${response.candidates.size} candidates, error=${response.error}")

                    if (response.hasError && response.error == "AREA_NOT_FOUND") {
                        _state.value = PlaceSearchState.NoResults(
                            radiusKm = response.radiusKm,
                            canExpand = false,
                            error = "Could not find location: $area"
                        )
                    } else if (response.isEmpty) {
                        _state.value = PlaceSearchState.NoResults(
                            radiusKm = response.radiusKm,
                            canExpand = response.canExpand,
                            error = null
                        )
                    } else {
                        val resultsState = PlaceSearchState.Results(
                            radiusKm = response.radiusKm,
                            candidates = response.candidates,
                            selectedPlaceId = null,
                            canExpand = response.canExpand,
                            message = null
                        )
                        lastResults = resultsState
                        _state.value = resultsState
                    }
                },
                onFailure = { error ->
                    Log.e(TAG, "Search failed", error)
                    _state.value = PlaceSearchState.Error(
                        message = error.message ?: "Search failed"
                    )
                }
            )
        }
    }

    /**
     * Expand the search radius.
     * Only available when current radius < 100km.
     */
    fun expandRadius() {
        val nextRadius = when (currentRadiusKm) {
            INITIAL_RADIUS_KM -> EXPANDED_RADIUS_KM
            EXPANDED_RADIUS_KM -> MAX_RADIUS_KM
            else -> return // Already at max
        }
        searchPlaces(nextRadius)
    }

    /**
     * Select a place candidate (highlight in UI).
     */
    fun selectCandidate(candidate: PlaceCandidate) {
        val current = _state.value
        if (current is PlaceSearchState.Results) {
            _state.value = current.copy(selectedPlaceId = candidate.placeId)
        }
    }

    /**
     * Confirm the selected place and fetch details.
     * Validates that the place has a valid E.164 phone number.
     */
    fun confirmSelection() {
        val current = _state.value
        if (current !is PlaceSearchState.Results || current.selectedCandidate == null) {
            Log.w(TAG, "confirmSelection called without valid selection")
            return
        }

        val candidate = current.selectedCandidate!!
        _state.value = PlaceSearchState.Resolving(
            placeId = candidate.placeId,
            placeName = candidate.name
        )

        viewModelScope.launch {
            Log.d(TAG, "Fetching details for: ${candidate.name}")

            val result = placesRepository.getPlaceDetails(candidate.placeId)

            result.fold(
                onSuccess = { details ->
                    if (details.hasValidPhone && details.phoneE164 != null) {
                        Log.d(TAG, "Place resolved: ${details.name}, phone=${details.phoneE164}")

                        _state.value = PlaceSearchState.Resolved(
                            businessName = details.name,
                            formattedAddress = details.formattedAddress,
                            phoneE164 = details.phoneE164,
                            placeId = details.placeId
                        )
                    } else {
                        Log.w(TAG, "Place has no valid phone: ${details.name}, error=${details.error}")
                        _state.value = PlaceSearchState.Error(
                            message = "This place doesn't have a valid phone number. Please select another."
                        )
                    }
                },
                onFailure = { error ->
                    Log.e(TAG, "Place details failed", error)
                    _state.value = PlaceSearchState.Error(
                        message = "Could not get place details: ${error.message}"
                    )
                }
            )
        }
    }

    /**
     * Return to results from error state.
     */
    fun backToResults() {
        lastResults?.let {
            _state.value = it.copy(selectedPlaceId = null)
        }
    }

    /**
     * Get the resolved place data.
     * Only valid when state is Resolved.
     *
     * DEBUG GUARD: Crashes in debug builds if called without valid phoneE164.
     */
    fun getResolvedPlace(): PlaceSearchState.Resolved? {
        val current = _state.value
        if (current is PlaceSearchState.Resolved) {
            // Debug guard: crash if phoneE164 is blank
            if (BuildConfig.ENABLE_LOCAL_LOGIC_GUARD && current.phoneE164.isBlank()) {
                throw RuntimeException("Place selection required before proceeding - phoneE164 is blank")
            }
            return current
        }
        return null
    }
}
