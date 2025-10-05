"""FastAPI server for story map visualization."""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sklearn.cluster import DBSCAN

# Database path - configurable via environment variable for easy swapping
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent.parent / "full_book.sqlite"))

# Validate environment on startup
if not DB_PATH.exists():
    print(f"ERROR: Database not found at {DB_PATH}", file=sys.stderr)
    print(f"Please ensure the database exists before starting the server.", file=sys.stderr)
    sys.exit(1)

app = FastAPI(title="Story Map API", description="API for visualizing geocoded stories on a map", version="1.0.0")

# Enable CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Get database connection with automatic cleanup."""
    if not DB_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def zoom_to_epsilon(zoom: int) -> float:
    """
    Map zoom level to DBSCAN epsilon (in radians for haversine metric).

    Zoom levels (Google Maps):
    1-4: World view (separate continents/countries)
    5-7: Regional view (states/regions within country)
    8-10: City view
    11-13: Neighborhood view
    14-16: Street/building view (tight clustering for overlapping markers)
    17+: Individual markers

    Returns epsilon in radians for haversine distance.
    """
    # Convert km to radians: radians = km / earth_radius_km
    EARTH_RADIUS_KM = 6371

    if zoom <= 3:
        return 2000 / EARTH_RADIUS_KM  # ~2000km - cluster country-level locations
    elif zoom <= 4:
        return 500 / EARTH_RADIUS_KM  # ~500km - separate coasts/regions
    elif zoom <= 7:
        return 100 / EARTH_RADIUS_KM  # ~100km - regional clusters
    elif zoom <= 9:
        return 20 / EARTH_RADIUS_KM  # ~20km - city clusters
    elif zoom <= 11:
        return 5 / EARTH_RADIUS_KM  # ~5km - neighborhood clusters
    elif zoom <= 13:
        return 1 / EARTH_RADIUS_KM  # ~1km - block-level clusters
    elif zoom <= 14:
        return 0.1 / EARTH_RADIUS_KM  # ~100m - building clusters
    elif zoom <= 15:
        return 0.05 / EARTH_RADIUS_KM  # ~50m - tight building clusters
    elif zoom <= 16:
        return 0.01 / EARTH_RADIUS_KM  # ~10m - same-location clusters
    else:
        return 0.0  # No clustering, show individual markers


def cluster_locations(locations: list[dict], epsilon_radians: float, min_samples: int = 2) -> tuple[list[dict], list[dict]]:
    """
    Cluster locations using DBSCAN.

    Args:
        locations: List of dicts with 'lat', 'lon', 'story_id', etc.
        epsilon_radians: DBSCAN epsilon in radians (for haversine metric)
        min_samples: Minimum samples per cluster

    Returns:
        Tuple of (clusters, noise_points):
        - clusters: List of cluster dicts with center_lat, center_lon, stories, etc.
        - noise_points: List of individual locations that didn't cluster
    """
    if not locations:
        return [], []

    # Extract coordinates
    coords = np.array([[loc["lat"], loc["lon"]] for loc in locations])

    # Run DBSCAN (using haversine metric with radians)
    clustering = DBSCAN(eps=epsilon_radians, min_samples=min_samples, metric="haversine").fit(np.radians(coords))

    # Group locations by cluster
    clusters = {}
    noise_points = []
    for idx, label in enumerate(clustering.labels_):
        if label == -1:  # Noise point - treat as individual location
            noise_points.append(locations[idx])
            continue
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(locations[idx])

    # Build cluster objects
    result = []
    for label, cluster_locs in clusters.items():
        # Calculate center
        center_lat = np.mean([loc["lat"] for loc in cluster_locs])
        center_lon = np.mean([loc["lon"] for loc in cluster_locs])

        # Deduplicate stories by story_id (same story can have multiple locations)
        seen_ids = set()
        unique_stories = []
        for loc in cluster_locs:
            if loc["story_id"] not in seen_ids:
                seen_ids.add(loc["story_id"])
                unique_stories.append(loc)

        # Extract date range efficiently (single pass)
        dates = [loc.get("date") for loc in unique_stories if loc.get("date")]
        if dates:
            min_date = max_date = dates[0]
            for date in dates[1:]:
                if date < min_date:
                    min_date = date
                if date > max_date:
                    max_date = date
            date_range = f"{min_date}–{max_date}"
            print(f"[DEBUG] Cluster date range: {date_range} (from {len(dates)} dated stories out of {len(unique_stories)} total)")
        else:
            date_range = None

        result.append({
            "center_lat": float(center_lat),
            "center_lon": float(center_lon),
            "story_count": len(unique_stories),
            "stories": unique_stories,
            "date_range": date_range,
        })

    return result, noise_points


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": "Story Map API",
        "version": "1.0.0",
        "endpoints": {
            "/api/locations": "Get locations and clusters for current viewport",
            "/api/story/{story_id}": "Get full story details",
            "/api/cluster/{cluster_id}": "Get cluster details with stories",
        },
    }


@app.get("/api/locations")
def get_locations(
    zoom: int = Query(..., description="Current zoom level (1-18)"),
    sw_lat: float = Query(..., description="Southwest latitude"),
    sw_lon: float = Query(..., description="Southwest longitude"),
    ne_lat: float = Query(..., description="Northeast latitude"),
    ne_lon: float = Query(..., description="Northeast longitude"),
) -> dict[str, Any]:
    """
    Get locations and clusters for current viewport and zoom level.

    Dynamic clustering approach:
    - Zoom 1-16: Cluster locations with zoom-appropriate epsilon
    - Zoom 17+: Return individual location markers

    All filtered by viewport bounds.
    """
    response: dict[str, Any] = {"locations": [], "clusters": []}

    print(f"[DEBUG] /api/locations: zoom={zoom}, bounds=({sw_lat}, {sw_lon}) to ({ne_lat}, {ne_lon})")

    try:
        with get_db() as conn:
            # Determine minimum precision based on zoom level
            # At world view (1-3): show all precisions
            # At regional view and closer (4+): hide country-level (too vague)
            precision_condition = "" if zoom <= 3 else "AND sl.resolved_precision != 'country'"

            # Fetch all locations in viewport
            query = f"""
                SELECT
                    sl.story_id,
                    sl.place_name,
                    sl.resolved_lat,
                    sl.resolved_lon,
                    sl.resolved_address,
                    sl.resolved_precision,
                    sl.resolution_confidence,
                    s.title,
                    s.summary,
                    s.parsed_date
                FROM story_locations sl
                JOIN stories s ON sl.story_id = s.story_id
                WHERE sl.resolved_lat IS NOT NULL
                  AND sl.resolved_lat BETWEEN ? AND ?
                  AND sl.resolved_lon BETWEEN ? AND ?
                  {precision_condition}
                ORDER BY sl.resolution_confidence DESC
            """

            cursor = conn.execute(query, (sw_lat, ne_lat, sw_lon, ne_lon))

            locations = []
            for row in cursor.fetchall():
                # Truncate summary for popup
                summary_preview = (row["summary"] or "")[:100]
                if len(row["summary"] or "") > 100:
                    summary_preview += "..."

                locations.append({
                    "story_id": row["story_id"],
                    "place_name": row["place_name"],
                    "lat": row["resolved_lat"],
                    "lon": row["resolved_lon"],
                    "address": row["resolved_address"],
                    "precision": row["resolved_precision"],
                    "confidence": row["resolution_confidence"],
                    "title": row["title"],
                    "summary_preview": summary_preview,
                    "date": row["parsed_date"],
                })

            print(f"[DEBUG] Found {len(locations)} locations in viewport")

            # Determine clustering strategy based on zoom
            epsilon = zoom_to_epsilon(zoom)

            if epsilon > 0:
                # Cluster the locations
                clusters, noise_points = cluster_locations(locations, epsilon, min_samples=2)
                print(f"[DEBUG] Clustered into {len(clusters)} clusters and {len(noise_points)} individual markers at zoom {zoom} (epsilon={epsilon})")

                # Add cluster IDs and format response
                for i, cluster in enumerate(clusters):
                    cluster["cluster_id"] = f"dynamic_{zoom}_{i}"

                    # Generate meaningful summary with location context
                    cluster_stories = cluster["stories"]
                    location_names = set()
                    for loc in cluster_stories[:5]:  # Sample first 5 for location names
                        if loc.get("place_name"):
                            # Extract city/area from place name
                            parts = loc["place_name"].split(",")
                            location_names.add(parts[0].strip())

                    location_str = ", ".join(list(location_names)[:3]) if location_names else "this area"
                    date_str = f" ({cluster['date_range']})" if cluster.get('date_range') else ""
                    cluster["summary"] = f"{cluster['story_count']} stories in {location_str}{date_str}"

                response["clusters"] = clusters
                response["locations"] = noise_points  # Include unclustered locations
            else:
                # Show individual markers (zoom >= 17)
                print(f"[DEBUG] Showing {len(locations)} individual markers at zoom {zoom}")
                response["locations"] = locations

    except sqlite3.Error as e:
        print(f"[ERROR] Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    return response


@app.get("/api/story/{story_id}")
def get_story(story_id: str) -> dict[str, Any]:
    """
    Get full story details.

    Returns:
        - story_id, title, summary, parsed_date
        - locations: list of locations
        - people: list of people
        - companies: list of companies
        - products: list of products
    """
    try:
        with get_db() as conn:
            # Get story
            cursor = conn.execute(
                """
                SELECT
                    story_id,
                    title,
                    summary,
                    parsed_date,
                    confidence
                FROM stories
                WHERE story_id = ?
            """,
                (story_id,),
            )

            story_row = cursor.fetchone()
            if not story_row:
                raise HTTPException(status_code=404, detail=f"Story {story_id} not found")

            story = {
                "story_id": story_row["story_id"],
                "title": story_row["title"],
                "summary": story_row["summary"],
                "parsed_date": story_row["parsed_date"],
                "confidence": story_row["confidence"],
            }

            # Get locations
            cursor = conn.execute(
                """
                SELECT place_name, resolved_lat, resolved_lon, resolved_address
                FROM story_locations
                WHERE story_id = ?
                ORDER BY loc_idx
            """,
                (story_id,),
            )
            story["locations"] = [
                {
                    "place_name": row["place_name"],
                    "lat": row["resolved_lat"],
                    "lon": row["resolved_lon"],
                    "address": row["resolved_address"],
                }
                for row in cursor.fetchall()
            ]

            # Get people
            cursor = conn.execute(
                """
                SELECT name, role_at_time, team, affiliation
                FROM story_people
                WHERE story_id = ?
                ORDER BY person_idx
            """,
                (story_id,),
            )
            story["people"] = [
                {
                    "name": row["name"],
                    "role": row["role_at_time"],
                    "team": row["team"],
                    "affiliation": row["affiliation"],
                }
                for row in cursor.fetchall()
            ]

            # Get companies
            cursor = conn.execute(
                """
                SELECT name, relationship
                FROM story_companies
                WHERE story_id = ?
                ORDER BY company_idx
            """,
                (story_id,),
            )
            story["companies"] = [{"name": row["name"], "relationship": row["relationship"]} for row in cursor.fetchall()]

            # Get products
            cursor = conn.execute(
                """
                SELECT product_line, model, codename, generation, design_language
                FROM story_products
                WHERE story_id = ?
                ORDER BY product_idx
            """,
                (story_id,),
            )
            story["products"] = [
                {
                    "product_line": row["product_line"],
                    "model": row["model"],
                    "codename": row["codename"],
                    "generation": row["generation"],
                    "design_language": row["design_language"],
                }
                for row in cursor.fetchall()
            ]

            return story

    except HTTPException:
        raise
    except sqlite3.Error as e:
        print(f"[ERROR] Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/api/cluster/{cluster_id}")
def get_cluster(cluster_id: str) -> dict[str, Any]:
    """
    Get cluster details with all stories.

    For dynamic clusters (cluster_id starts with "dynamic_"), returns the stories
    that would be in that cluster. This is a lightweight endpoint since we don't
    have pre-computed summaries.

    Returns:
        - cluster_id, center_lat, center_lon
        - summary, date_range, story_count
        - stories: list of stories with timeline data
    """
    # Dynamic clusters are identified by their ID format: "dynamic_{zoom}_{index}"
    # For now, we'll return a simple error since the frontend passes the full stories
    # in the cluster object already. This endpoint is mainly for future expansion.

    raise HTTPException(
        status_code=501,
        detail="Dynamic cluster details not yet implemented. Cluster data is included in /api/locations response."
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
