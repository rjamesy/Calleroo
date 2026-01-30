"""
Google Places Service for Calleroo.
Handles geocoding, text search, and place details.

This service is DETERMINISTIC - NO OpenAI calls.
All place data comes directly from Google Places API.

Python 3.9 compatible - uses typing.Dict, typing.List, typing.Optional
"""

import logging
import os
import re
from typing import List, Optional, Tuple

import httpx

from .models import PlaceCandidate, PlaceSearchResponse, PlaceDetailsResponse

logger = logging.getLogger(__name__)


class GooglePlacesService:
    """Service for Google Places API operations."""

    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

    # Allowed radius values in km
    ALLOWED_RADII = [25, 50, 100]

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise RuntimeError("GOOGLE_PLACES_API_KEY is required for Places service")

        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("Google Places service initialized")

    async def close(self):
        """Close the HTTP client."""
        await self.http_client.aclose()
        logger.info("Google Places service closed")

    async def geocode_area(self, area: str, country: str) -> Optional[Tuple[float, float]]:
        """
        Geocode an area name to lat/lng coordinates.

        Args:
            area: Area name like "Browns Plains" or "Richmond VIC"
            country: Country code like "AU"

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        params = {
            "address": f"{area} {country}",
            "key": self.api_key,
        }

        try:
            response = await self.http_client.get(self.GEOCODE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "OK" and data.get("results"):
                location = data["results"][0]["geometry"]["location"]
                lat, lng = location["lat"], location["lng"]
                logger.debug(f"Geocoded '{area} {country}' to ({lat}, {lng})")
                return (lat, lng)

            logger.warning(f"Geocoding failed for '{area} {country}': {data.get('status')}")
            return None

        except Exception as e:
            logger.error(f"Geocoding error for '{area} {country}': {e}")
            return None

    async def text_search(
        self,
        query: str,
        area: str,
        country: str,
        radius_km: int
    ) -> PlaceSearchResponse:
        """
        Search for places using Google Places Text Search API.

        Uses area geocoding to bias results toward the specified location.
        NO GPS/device location is used - only the area string.

        Args:
            query: Search query (e.g., "JB Hi-Fi" or "Thai Palace restaurant")
            area: Area to search in (e.g., "Browns Plains" or "Richmond VIC")
            country: Country code (default "AU")
            radius_km: Search radius in kilometers (25, 50, or 100)

        Returns:
            PlaceSearchResponse with candidates or error
        """
        # Coerce radius to allowed values
        if radius_km not in self.ALLOWED_RADII:
            logger.warning(f"Invalid radius {radius_km}km, coercing to 25km")
            radius_km = 25

        # Geocode the area first to get coordinates for location bias
        coords = await self.geocode_area(area, country)
        if not coords:
            logger.warning(f"Could not geocode area '{area}', returning AREA_NOT_FOUND")
            return PlaceSearchResponse(
                radiusKm=radius_km,
                candidates=[],
                error="AREA_NOT_FOUND"
            )

        lat, lng = coords
        radius_m = radius_km * 1000

        # Build the search query - include area in query string for better results
        search_query = f"{query} {area} {country}"

        params = {
            "query": search_query,
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "key": self.api_key,
        }

        try:
            response = await self.http_client.get(self.TEXT_SEARCH_URL, params=params)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status not in ["OK", "ZERO_RESULTS"]:
                logger.error(f"Places API error: {status}")
                return PlaceSearchResponse(
                    radiusKm=radius_km,
                    candidates=[],
                    error="PLACES_ERROR"
                )

            # Parse results - max 10 candidates
            candidates: List[PlaceCandidate] = []
            for result in data.get("results", [])[:10]:
                place_id = result.get("place_id")
                name = result.get("name")

                # Skip results missing required fields
                if not place_id or not name:
                    continue

                location = result.get("geometry", {}).get("location", {})

                candidate = PlaceCandidate(
                    placeId=place_id,
                    name=name,
                    formattedAddress=result.get("formatted_address"),
                    lat=location.get("lat"),
                    lng=location.get("lng")
                )
                candidates.append(candidate)

            logger.info(f"Text search for '{query}' near '{area}': {len(candidates)} candidates")
            return PlaceSearchResponse(
                radiusKm=radius_km,
                candidates=candidates,
                error=None
            )

        except Exception as e:
            logger.error(f"Text search error: {e}")
            return PlaceSearchResponse(
                radiusKm=radius_km,
                candidates=[],
                error="PLACES_ERROR"
            )

    async def place_details(self, place_id: str) -> PlaceDetailsResponse:
        """
        Get detailed information about a specific place.

        Fetches phone number and normalizes to E.164 format.

        Args:
            place_id: Google Place ID

        Returns:
            PlaceDetailsResponse with phone number or error
        """
        params = {
            "place_id": place_id,
            "fields": "place_id,name,formatted_address,international_phone_number,formatted_phone_number",
            "key": self.api_key,
        }

        try:
            response = await self.http_client.get(self.PLACE_DETAILS_URL, params=params)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status != "OK" or not data.get("result"):
                logger.warning(f"Place details failed for {place_id}: {status}")
                return PlaceDetailsResponse(
                    placeId=place_id,
                    name="",
                    error="PLACE_NOT_FOUND"
                )

            result = data["result"]
            name = result.get("name", "")
            formatted_address = result.get("formatted_address")

            # Get phone number - prefer international format
            raw_phone = (
                result.get("international_phone_number") or
                result.get("formatted_phone_number")
            )

            # Normalize to E.164
            phone_e164 = self._normalize_to_e164(raw_phone)

            if not phone_e164:
                logger.warning(f"Place {name} has no valid phone number")
                return PlaceDetailsResponse(
                    placeId=place_id,
                    name=name,
                    formattedAddress=formatted_address,
                    phoneE164=None,
                    error="NO_PHONE"
                )

            logger.info(f"Place details for {name}: phone={phone_e164}")
            return PlaceDetailsResponse(
                placeId=place_id,
                name=name,
                formattedAddress=formatted_address,
                phoneE164=phone_e164,
                error=None
            )

        except Exception as e:
            logger.error(f"Place details error for {place_id}: {e}")
            return PlaceDetailsResponse(
                placeId=place_id,
                name="",
                error="PLACES_ERROR"
            )

    def _normalize_to_e164(self, phone: Optional[str]) -> Optional[str]:
        """
        Normalize phone number to E.164 format.

        E.164 format: +[country code][subscriber number]
        Example: +61412345678

        Args:
            phone: Raw phone number string

        Returns:
            E.164 formatted phone or None if invalid/missing
        """
        if not phone:
            return None

        # Remove spaces, hyphens, parentheses
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)

        # Already in E.164 format (starts with + and has enough digits)
        if cleaned.startswith('+') and len(cleaned) >= 8:
            # Validate it looks like a phone number
            if re.match(r'^\+\d{7,15}$', cleaned):
                return cleaned

        # Try to normalize Australian numbers
        digits = re.sub(r'[^\d]', '', cleaned)

        # Australian format: starts with 0, 10 digits total (e.g., 0412345678)
        if digits.startswith('0') and len(digits) == 10:
            return f"+61{digits[1:]}"

        # Australian without leading 0: 9 digits (e.g., 412345678)
        if len(digits) == 9 and digits[0] in '234789':
            return f"+61{digits}"

        # Australian landline: 8 digits with area code implied
        if len(digits) == 8:
            # Could be landline without area code - can't reliably normalize
            return None

        logger.debug(f"Could not normalize phone: {phone}")
        return None
