"""Core geocoding resolver - orchestrates BAML, web search, and geocoding."""

import asyncio
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

# Add project root to path for baml_client imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from abxgeo.geocoder import GeocoderCascade
from abxgeo.rate_limiter import GOOGLE_MAPS_LIMITER, NOMINATIM_LIMITER, OPENAI_LIMITER
from baml_client import b


class LocationResolver:
    """Resolves vague locations to precise addresses using LLM + web search + geocoding."""

    def __init__(
        self,
        db_path: str,
        user_email: str,
        google_api_key: str | None = None,
        verbose: bool = False,
    ):
        """
        Initialize resolver.

        Args:
            db_path: Path to SQLite database
            user_email: Email for Nominatim user agent
            google_api_key: Optional Google Maps API key (also reads from GOOGLE_MAPS_API_KEY env var)
            verbose: Print detailed logs
        """
        self.db_path = db_path
        self.user_email = user_email
        self.verbose = verbose

        # Get Google API key from env if not provided
        if google_api_key is None:
            import os

            google_api_key = os.environ.get("GOOGLE_MAPS_API_KEY")

        # Initialize geocoder
        self.geocoder = GeocoderCascade(
            user_agent=f"ABXGeo/1.0 ({user_email})",
            google_api_key=google_api_key,
        )

        if self.verbose and google_api_key:
            print("✓ Google Maps API key configured (cascade: Google → Nominatim)")
        elif self.verbose:
            print("⚠ No Google Maps API key (using Nominatim only)")

    def resolve(
        self,
        story_id: str,
        loc_idx: int,
        place_name: str,
        place_type: str | None,
        note: str | None,
        lat: float | None,
        lon: float | None,
        geo_precision: str | None,
        story_title: str,
        story_summary: str,
    ) -> dict | None:
        """
        Resolve a location to precise address.

        Args:
            story_id: Story ID
            loc_idx: Location index within story
            place_name: Location name
            place_type: Location type
            note: Context note
            lat: Approximate latitude (if available)
            lon: Approximate longitude (if available)
            geo_precision: Current precision level
            story_title: Story title for context
            story_summary: Story summary for context

        Returns:
            Resolution result dictionary or None if failed
        """
        if self.verbose:
            print(f"\n=== Resolving: {place_name} ===")
            print(f"Type: {place_type}, Note: {note}")

        # Step 1: Find precise address using BAML with web search
        try:
            address_resolution = asyncio.run(
                b.FindPreciseAddress(
                    place_name=place_name,
                    place_type=place_type,
                    note=note,
                    story_title=story_title,
                    story_summary=story_summary,
                    original_lat=lat,
                    original_lon=lon,
                )
            )

            if self.verbose:
                print(f"Found address: {address_resolution.address}")
                print(f"Confidence: {address_resolution.confidence}")
                print(f"Precision: {address_resolution.precision}")
                print(f"Corroboration: {address_resolution.corroboration}")
                print(f"Concerns: {address_resolution.concerns}")

        except Exception as e:
            print(f"Failed to find address: {e}")
            return None

        # Step 2: Geocode the address for precise coordinates
        geocode_result = None
        if address_resolution.address:
            try:
                geocode_result = self.geocoder.geocode(address_resolution.address)

                if geocode_result and self.verbose:
                    print(f"Geocoded: {geocode_result['address']}")
                    print(f"Coords: ({geocode_result['lat']}, {geocode_result['lon']})")
                    print(f"Precision: {geocode_result['precision']}")

            except Exception as e:
                print(f"Failed to geocode: {e}")

        # Step 3: Build resolution result
        result = {
            "story_id": story_id,
            "loc_idx": loc_idx,
            "resolved_address": address_resolution.address,
            "resolved_lat": geocode_result["lat"] if geocode_result else address_resolution.lat,
            "resolved_lon": geocode_result["lon"] if geocode_result else address_resolution.lon,
            "resolved_precision": geocode_result["precision"] if geocode_result else address_resolution.precision,
            "resolution_confidence": address_resolution.confidence,
            "resolution_source": json.dumps(
                {
                    "url": address_resolution.source_url,
                    "snippet": address_resolution.source_snippet,
                    "geocoder": geocode_result["source"] if geocode_result else None,
                    "is_residence": address_resolution.is_residence,
                    "corroboration": address_resolution.corroboration,
                    "concerns": address_resolution.concerns,
                }
            ),
            "resolved_at": datetime.now().isoformat(),
        }

        return result

    def persist_resolution(self, resolution: dict) -> None:
        """
        Persist resolution result to database.

        Args:
            resolution: Resolution result from resolve()
        """
        # Calculate resolution hash for idempotency
        hash_input = f"{resolution['story_id']}:{resolution['loc_idx']}:{resolution['resolved_address']}"
        resolution_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE story_locations
                SET
                    resolved_address = ?,
                    resolved_lat = ?,
                    resolved_lon = ?,
                    resolved_precision = ?,
                    resolution_confidence = ?,
                    resolution_source = ?,
                    resolved_at = ?,
                    resolution_hash = ?
                WHERE story_id = ? AND loc_idx = ?
                """,
                (
                    resolution["resolved_address"],
                    resolution["resolved_lat"],
                    resolution["resolved_lon"],
                    resolution["resolved_precision"],
                    resolution["resolution_confidence"],
                    resolution["resolution_source"],
                    resolution["resolved_at"],
                    resolution_hash,
                    resolution["story_id"],
                    resolution["loc_idx"],
                ),
            )
            conn.commit()

        if self.verbose:
            print(f"✓ Persisted resolution for {resolution['story_id']}:{resolution['loc_idx']}")

    def should_skip_resolution(
        self,
        story_id: str,
        loc_idx: int,
        resolved_address: str | None,
        resolution_confidence: float | None,
        incremental: bool,
    ) -> bool:
        """
        Check if location should be skipped.

        Args:
            story_id: Story ID
            loc_idx: Location index
            resolved_address: Current resolved address
            resolution_confidence: Current confidence score
            incremental: Whether running in incremental mode

        Returns:
            True if should skip, False otherwise
        """
        # Always resolve if no address
        if not resolved_address:
            return False

        # In incremental mode, skip if confidence is high
        if incremental and resolution_confidence and resolution_confidence >= 0.7:
            if self.verbose:
                print(f"Skipping {story_id}:{loc_idx} (already resolved with confidence {resolution_confidence})")
            return True

        return False

    async def resolve_async(
        self,
        story_id: str,
        loc_idx: int,
        place_name: str,
        place_type: str | None,
        note: str | None,
        lat: float | None,
        lon: float | None,
        geo_precision: str | None,
        story_title: str,
        story_summary: str,
    ) -> dict | None:
        """
        Async version of resolve() for parallel processing.

        Same arguments and return value as resolve(), but uses native async/await.
        """
        if self.verbose:
            print(f"\n=== Resolving: {place_name} ===")
            print(f"Type: {place_type}, Note: {note}")

        # Step 0: Classify location to determine processing tier
        classification = None
        try:
            async with OPENAI_LIMITER:
                classification = await b.ClassifyLocation(
                    place_name=place_name,
                    place_type=place_type,
                    note=note,
                    story_title=story_title,
                    story_summary=story_summary,
                )

            if self.verbose:
                print(f"Classification: {classification.category} - {classification.reason}")

        except Exception as e:
            if self.verbose:
                print(f"⚠ Classification failed: {str(e)[:100]}, falling back to research tier")
            classification = None

        # Handle SKIP tier: Return immediately with low confidence
        if classification and classification.category == "skip":
            if self.verbose:
                print(f"→ Skipping (vague location): {classification.reason}")

            return {
                "story_id": story_id,
                "loc_idx": loc_idx,
                "resolved_address": place_name,
                "resolved_lat": lat,
                "resolved_lon": lon,
                "resolved_precision": "country" if place_type == "country" else "region",
                "resolution_confidence": 0.2,
                "resolution_source": json.dumps({
                    "tier": "skip",
                    "reason": classification.reason,
                    "url": "N/A",
                    "snippet": "N/A",
                    "geocoder": None,
                    "is_residence": False,
                    "corroboration": [],
                    "concerns": ["Location too vague - insufficient context for specific address"],
                }),
                "resolved_at": datetime.now().isoformat(),
            }

        # Handle SIMPLE tier: Just geocode the well-known address
        if classification and classification.category == "simple" and classification.simple_address:
            if self.verbose:
                print(f"→ Simple lookup: {classification.simple_address}")

            geocode_result = None
            try:
                if self.geocoder.google:
                    async with GOOGLE_MAPS_LIMITER:
                        geocode_result = await asyncio.to_thread(self.geocoder.geocode, classification.simple_address)
                else:
                    async with NOMINATIM_LIMITER:
                        geocode_result = await asyncio.to_thread(self.geocoder.geocode, classification.simple_address)

                if geocode_result and self.verbose:
                    print(f"Geocoded: {geocode_result['address']}")
                    print(f"Coords: ({geocode_result['lat']}, {geocode_result['lon']})")

            except Exception as e:
                if self.verbose:
                    print(f"⚠ Simple geocoding failed: {str(e)[:100]}")

            # Return simple tier result
            return {
                "story_id": story_id,
                "loc_idx": loc_idx,
                "resolved_address": geocode_result["address"] if geocode_result else classification.simple_address,
                "resolved_lat": geocode_result["lat"] if geocode_result else lat,
                "resolved_lon": geocode_result["lon"] if geocode_result else lon,
                "resolved_precision": geocode_result["precision"] if geocode_result else classification.estimated_precision or "city",
                "resolution_confidence": 0.85,  # High confidence for well-known places
                "resolution_source": json.dumps({
                    "tier": "simple",
                    "reason": classification.reason,
                    "url": "N/A (well-known location)",
                    "snippet": "N/A",
                    "geocoder": geocode_result["source"] if geocode_result else None,
                    "is_residence": False,
                    "corroboration": [],
                    "concerns": [],
                }),
                "resolved_at": datetime.now().isoformat(),
            }

        # RESEARCH tier: Use GPT-5 with web search (original expensive path)
        if self.verbose:
            print("→ Research tier: Using GPT-5 with web search")

        # Step 1: Find precise address using BAML with web search (with rate limiting and retry)
        max_retries = 3
        retry_delay = 1  # Start with 1 second

        for attempt in range(max_retries):
            try:
                async with OPENAI_LIMITER:
                    address_resolution = await b.FindPreciseAddress(
                        place_name=place_name,
                        place_type=place_type,
                        note=note,
                        story_title=story_title,
                        story_summary=story_summary,
                        original_lat=lat,
                        original_lon=lon,
                    )

                if self.verbose:
                    print(f"Found address: {address_resolution.address}")
                    print(f"Confidence: {address_resolution.confidence}")
                    print(f"Precision: {address_resolution.precision}")
                    print(f"Corroboration: {address_resolution.corroboration}")
                    print(f"Concerns: {address_resolution.concerns}")

                # Success - break out of retry loop
                break

            except Exception as e:
                error_msg = str(e)
                is_retryable = (
                    "broken pipe" in error_msg.lower()
                    or "connection" in error_msg.lower()
                    or "timeout" in error_msg.lower()
                    or "rate limit" in error_msg.lower()
                )

                if attempt < max_retries - 1 and is_retryable:
                    print(f"⚠ Attempt {attempt + 1} failed: {error_msg[:100]}")
                    print(f"  Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print(f"Failed to find address after {attempt + 1} attempts: {error_msg[:200]}")
                    return None

        # Step 2: Geocode the address for precise coordinates (run in thread pool with rate limiting and retry)
        geocode_result = None
        if address_resolution.address:
            max_geocode_retries = 2
            geocode_delay = 1

            for attempt in range(max_geocode_retries):
                try:
                    # Use appropriate rate limiter based on geocoder
                    if self.geocoder.google:
                        async with GOOGLE_MAPS_LIMITER:
                            geocode_result = await asyncio.to_thread(self.geocoder.geocode, address_resolution.address)
                    else:
                        async with NOMINATIM_LIMITER:
                            geocode_result = await asyncio.to_thread(self.geocoder.geocode, address_resolution.address)

                    if geocode_result and self.verbose:
                        print(f"Geocoded: {geocode_result['address']}")
                        print(f"Coords: ({geocode_result['lat']}, {geocode_result['lon']})")
                        print(f"Precision: {geocode_result['precision']}")

                    # Success - break out of retry loop
                    break

                except Exception as e:
                    error_msg = str(e)
                    if attempt < max_geocode_retries - 1:
                        print(f"⚠ Geocoding attempt {attempt + 1} failed: {error_msg[:100]}")
                        print(f"  Retrying in {geocode_delay}s...")
                        await asyncio.sleep(geocode_delay)
                        geocode_delay *= 2
                    else:
                        print(f"Failed to geocode after {attempt + 1} attempts: {error_msg[:200]}")

        # Step 3: Build resolution result
        result = {
            "story_id": story_id,
            "loc_idx": loc_idx,
            "resolved_address": address_resolution.address,
            "resolved_lat": geocode_result["lat"] if geocode_result else address_resolution.lat,
            "resolved_lon": geocode_result["lon"] if geocode_result else address_resolution.lon,
            "resolved_precision": geocode_result["precision"] if geocode_result else address_resolution.precision,
            "resolution_confidence": address_resolution.confidence,
            "resolution_source": json.dumps(
                {
                    "url": address_resolution.source_url,
                    "snippet": address_resolution.source_snippet,
                    "geocoder": geocode_result["source"] if geocode_result else None,
                    "is_residence": address_resolution.is_residence,
                    "corroboration": address_resolution.corroboration,
                    "concerns": address_resolution.concerns,
                }
            ),
            "resolved_at": datetime.now().isoformat(),
        }

        return result

    async def resolve_batch(
        self,
        locations: list[dict],
        concurrency: int = 10,
    ) -> list[dict | None]:
        """
        Resolve multiple locations in parallel.

        Args:
            locations: List of location dictionaries (from SQL query)
            concurrency: Maximum number of concurrent resolutions

        Returns:
            List of resolution results (None for failed resolutions)
        """
        # Create semaphore for overall concurrency control
        semaphore = asyncio.Semaphore(concurrency)

        async def resolve_with_semaphore(loc):
            async with semaphore:
                try:
                    return await self.resolve_async(
                        story_id=loc["story_id"],
                        loc_idx=loc["loc_idx"],
                        place_name=loc["place_name"],
                        place_type=loc["place_type"],
                        note=loc["note"],
                        lat=loc["lat"],
                        lon=loc["lon"],
                        geo_precision=loc["geo_precision"],
                        story_title=loc["story_title"],
                        story_summary=loc["story_summary"],
                    )
                except Exception as e:
                    print(f"Error resolving {loc['place_name']}: {e}")
                    return None

        # Resolve all locations in parallel
        results = await asyncio.gather(*[resolve_with_semaphore(loc) for loc in locations], return_exceptions=True)

        # Convert exceptions to None
        return [r if not isinstance(r, Exception) else None for r in results]
