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
from abxgeo.web_harvester import WebHarvester
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

        # Initialize components
        self.harvester = WebHarvester(db_path)
        self.geocoder = GeocoderCascade(
            user_agent=f"ABXGeo/1.0 ({user_email})",
            google_api_key=google_api_key,
        )

        if self.verbose and google_api_key:
            print(f"✓ Google Maps API key configured (cascade: Google → Nominatim)")
        elif self.verbose:
            print(f"⚠ No Google Maps API key (using Nominatim only)")

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

        # Step 1: Generate search query using BAML
        try:
            search_query_obj = asyncio.run(
                b.GenerateSearchQuery(
                    place_name=place_name,
                    place_type=place_type,
                    note=note,
                    story_title=story_title,
                    story_summary=story_summary,
                )
            )
            search_query = search_query_obj.query

            if self.verbose:
                print(f"Search query: {search_query}")

        except Exception as e:
            print(f"Failed to generate search query: {e}")
            return None

        # Step 2: Search web and fetch content
        try:
            search_results = self.harvester.harvest(search_query, max_results=5)

            if self.verbose:
                print(f"Search results length: {len(search_results)} chars")

        except Exception as e:
            print(f"Failed to harvest web content: {e}")
            return None

        # Step 3: Extract address candidates using BAML
        try:
            story_context = f"{story_title}: {story_summary}"
            candidates = asyncio.run(
                b.ExtractAddressCandidates(
                    search_results=search_results,
                    place_name=place_name,
                    story_context=story_context,
                )
            )

            if self.verbose:
                print(f"Found {len(candidates)} candidates")
                for i, cand in enumerate(candidates, 1):
                    print(f"  {i}. {cand.address} (confidence: {cand.confidence})")

        except Exception as e:
            print(f"Failed to extract candidates: {e}")
            return None

        # If no candidates, return early
        if not candidates:
            if self.verbose:
                print("No candidates found")
            return None

        # Step 4: Score and validate using BAML
        try:
            original_coords = f"{lat},{lon}" if lat and lon else None
            scored = asyncio.run(
                b.ScoreAndValidate(
                    candidates=candidates,
                    place_name=place_name,
                    original_coords=original_coords,
                )
            )

            best_candidate = scored.candidate
            final_score = scored.final_score

            if self.verbose:
                print(f"Best candidate: {best_candidate.address}")
                print(f"Final score: {final_score}")
                print(f"Corroboration: {scored.corroboration}")
                print(f"Concerns: {scored.concerns}")

        except Exception as e:
            print(f"Failed to score candidates: {e}")
            return None

        # Step 5: Geocode the best candidate address
        geocode_result = None
        if best_candidate.address:
            try:
                geocode_result = self.geocoder.geocode(best_candidate.address)

                if geocode_result and self.verbose:
                    print(f"Geocoded: {geocode_result['address']}")
                    print(f"Coords: ({geocode_result['lat']}, {geocode_result['lon']})")
                    print(f"Precision: {geocode_result['precision']}")

            except Exception as e:
                print(f"Failed to geocode: {e}")

        # Step 6: Build resolution result
        result = {
            "story_id": story_id,
            "loc_idx": loc_idx,
            "resolved_address": best_candidate.address,
            "resolved_lat": geocode_result["lat"] if geocode_result else best_candidate.lat,
            "resolved_lon": geocode_result["lon"] if geocode_result else best_candidate.lon,
            "resolved_precision": geocode_result["precision"] if geocode_result else best_candidate.precision,
            "resolution_confidence": final_score,
            "resolution_source": json.dumps(
                {
                    "url": best_candidate.source_url,
                    "snippet": best_candidate.source_snippet,
                    "geocoder": geocode_result["source"] if geocode_result else None,
                    "is_residence": best_candidate.is_residence,
                    "corroboration": scored.corroboration,
                    "concerns": scored.concerns,
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
