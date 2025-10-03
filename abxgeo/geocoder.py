"""Geocoder cascade - tries Nominatim, then falls back to Google/Mapbox if needed."""

from geopy.geocoders import GoogleV3, Nominatim
from geopy.location import Location


class GeocoderCascade:
    """Geocodes addresses using a cascade of services."""

    def __init__(
        self,
        user_agent: str = "ABXGeo/1.0",
        google_api_key: str | None = None,
        mapbox_api_key: str | None = None,
    ):
        """
        Initialize geocoder cascade.

        Args:
            user_agent: User agent for Nominatim
            google_api_key: Google Maps API key (optional)
            mapbox_api_key: Mapbox API key (optional)
        """
        # Nominatim (free, no API key needed, but has rate limits)
        self.nominatim = Nominatim(user_agent=user_agent)

        # Google (requires API key, very accurate)
        self.google = GoogleV3(api_key=google_api_key) if google_api_key else None

        # Mapbox (requires API key, good alternative to Google)
        # Note: geopy doesn't have built-in Mapbox support, would need custom implementation
        self.mapbox_api_key = mapbox_api_key

    def geocode(self, address: str, timeout: int = 10) -> dict | None:
        """
        Geocode an address using cascade of services.

        Tries in order:
        1. Google Maps (if API key provided) - 10k free calls/month, superior accuracy
        2. Nominatim (free, OpenStreetMap) - fallback, respects rate limits
        3. Mapbox (if API key provided) - additional fallback

        Args:
            address: Address to geocode
            timeout: Timeout in seconds for each service

        Returns:
            Dictionary with:
                - address: Formatted address
                - lat: Latitude
                - lon: Longitude
                - precision: One of 'address', 'street', 'city', 'region', 'country'
                - source: Which geocoder was used
            Or None if geocoding failed
        """
        # Try Google first (10k free calls/month, best accuracy)
        if self.google:
            result = self._try_google(address, timeout)
            if result:
                return result

        # Fallback to Nominatim (free, but less accurate)
        result = self._try_nominatim(address, timeout)
        if result:
            return result

        # Could add Mapbox here if needed
        # if self.mapbox_api_key:
        #     result = self._try_mapbox(address, timeout)
        #     if result:
        #         return result

        return None

    def _try_nominatim(self, address: str, timeout: int) -> dict | None:
        """Try geocoding with Nominatim."""
        try:
            location: Location | None = self.nominatim.geocode(address, timeout=timeout, addressdetails=True)

            if not location:
                return None

            # Determine precision from address details
            precision = self._determine_precision_nominatim(location)

            return {
                "address": location.address,
                "lat": location.latitude,
                "lon": location.longitude,
                "precision": precision,
                "source": "nominatim",
            }

        except Exception as e:
            print(f"Nominatim geocoding failed for '{address}': {e}")
            return None

    def _try_google(self, address: str, timeout: int) -> dict | None:
        """Try geocoding with Google Maps."""
        if not self.google:
            return None

        try:
            location: Location | None = self.google.geocode(address, timeout=timeout)

            if not location:
                return None

            # Determine precision from location type
            precision = self._determine_precision_google(location)

            return {
                "address": location.address,
                "lat": location.latitude,
                "lon": location.longitude,
                "precision": precision,
                "source": "google",
            }

        except Exception as e:
            print(f"Google geocoding failed for '{address}': {e}")
            return None

    def _determine_precision_nominatim(self, location: Location) -> str:
        """Determine precision level from Nominatim result."""
        # Nominatim provides detailed address breakdown
        raw = getattr(location, "raw", {})
        address_details = raw.get("address", {})
        place_type = raw.get("type", "")

        # Check address components from most to least specific
        if "house_number" in address_details or place_type == "house":
            return "address"
        elif "road" in address_details or place_type in ("road", "street"):
            return "street"
        elif "city" in address_details or "town" in address_details or "village" in address_details:
            return "city"
        elif "state" in address_details or "region" in address_details:
            return "region"
        elif "country" in address_details:
            return "country"
        else:
            return "city"  # default fallback

    def _determine_precision_google(self, location: Location) -> str:
        """Determine precision level from Google result."""
        # Google provides location_type in raw data
        raw = getattr(location, "raw", {})
        geometry = raw.get("geometry", {})
        location_type = geometry.get("location_type", "")

        # Google's location types map to our precision levels
        if location_type == "ROOFTOP":
            return "address"
        elif location_type == "RANGE_INTERPOLATED":
            return "street"
        elif location_type == "GEOMETRIC_CENTER":
            # Check address components to determine if city or region
            address_components = raw.get("address_components", [])
            types = [t for comp in address_components for t in comp.get("types", [])]

            if "street_address" in types or "premise" in types:
                return "address"
            elif "route" in types:
                return "street"
            elif "locality" in types or "postal_town" in types:
                return "city"
            elif "administrative_area_level_1" in types:
                return "region"
            elif "country" in types:
                return "country"

        return "city"  # default fallback

    def reverse_geocode(self, lat: float, lon: float, timeout: int = 10) -> dict | None:
        """
        Reverse geocode coordinates to address.

        Args:
            lat: Latitude
            lon: Longitude
            timeout: Timeout in seconds

        Returns:
            Dictionary with address and precision, or None if failed
        """
        # Try Google first (10k free calls/month, best accuracy)
        if self.google:
            try:
                location: Location | None = self.google.reverse((lat, lon), timeout=timeout)

                if location:
                    precision = self._determine_precision_google(location)
                    return {
                        "address": location.address,
                        "lat": location.latitude,
                        "lon": location.longitude,
                        "precision": precision,
                        "source": "google",
                    }
            except Exception as e:
                print(f"Google reverse geocoding failed for ({lat}, {lon}): {e}")

        # Fallback to Nominatim
        try:
            location: Location | None = self.nominatim.reverse((lat, lon), timeout=timeout, addressdetails=True)

            if location:
                precision = self._determine_precision_nominatim(location)
                return {
                    "address": location.address,
                    "lat": location.latitude,
                    "lon": location.longitude,
                    "precision": precision,
                    "source": "nominatim",
                }
        except Exception as e:
            print(f"Nominatim reverse geocoding failed for ({lat}, {lon}): {e}")

        return None
