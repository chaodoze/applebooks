#!/usr/bin/env python3
"""Quick test of geocoding pipeline with one location."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from abxgeo.resolver import LocationResolver

# Test location
test_location = {
    "story_id": "test-001",
    "loc_idx": 0,
    "place_name": "Cupertino, California",
    "place_type": "city",
    "note": "Apple's headquarters location",
    "lat": None,
    "lon": None,
    "geo_precision": None,
    "story_title": "Test Story",
    "story_summary": "Testing geocoding for Apple headquarters in Cupertino",
}

# Initialize resolver
resolver = LocationResolver(
    db_path="full_book.sqlite",
    user_email="test@example.com",
    verbose=True,
)

print("=" * 80)
print("Testing geocoding pipeline with: Cupertino, California")
print("=" * 80)

# Resolve
try:
    result = resolver.resolve(
        story_id=test_location["story_id"],
        loc_idx=test_location["loc_idx"],
        place_name=test_location["place_name"],
        place_type=test_location["place_type"],
        note=test_location["note"],
        lat=test_location["lat"],
        lon=test_location["lon"],
        geo_precision=test_location["geo_precision"],
        story_title=test_location["story_title"],
        story_summary=test_location["story_summary"],
    )

    if result:
        print("\n" + "=" * 80)
        print("RESOLUTION SUCCESS")
        print("=" * 80)
        print(f"Address: {result['resolved_address']}")
        print(f"Coordinates: ({result['resolved_lat']}, {result['resolved_lon']})")
        print(f"Precision: {result['resolved_precision']}")
        print(f"Confidence: {result['resolution_confidence']}")
        print(f"Source: {result['resolution_source']}")
    else:
        print("\nRESOLUTION FAILED")

except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
