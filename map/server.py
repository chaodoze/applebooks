"""FastAPI server for story map visualization."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# Database path (relative to this file)
DB_PATH = Path(__file__).parent.parent / "full_book.sqlite"

app = FastAPI(title="Story Map API", description="API for visualizing geocoded stories on a map", version="1.0.0")

# Enable CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

    Logic:
    - If zoom < 8: Return clusters only (global/regional view)
    - If zoom >= 8: Return individual locations (city/street view)

    Both filtered by viewport bounds.
    """
    conn = get_db()

    response: dict[str, Any] = {"locations": [], "clusters": []}

    print(f"[DEBUG] /api/locations: zoom={zoom}, bounds=({sw_lat}, {sw_lon}) to ({ne_lat}, {ne_lon})")

    if zoom < 8:
        # Return all clusters (no filtering needed - overlaps handled by merge logic)
        cursor = conn.execute(
            """
            SELECT
                cluster_id,
                center_lat,
                center_lon,
                summary,
                key_themes_json,
                story_count,
                date_range,
                zoom_level
            FROM location_clusters
            WHERE center_lat BETWEEN ? AND ?
              AND center_lon BETWEEN ? AND ?
            ORDER BY story_count DESC
        """,
            (sw_lat, ne_lat, sw_lon, ne_lon),
        )

        all_rows = cursor.fetchall()
        print(f"[DEBUG] SQL returned {len(all_rows)} rows")

        clusters = []
        for row in all_rows:
            print(f"[DEBUG] Processing cluster {row['cluster_id']}, zoom={row['zoom_level']}, count={row['story_count']}")
            clusters.append(
                {
                    "cluster_id": row["cluster_id"],
                    "center_lat": row["center_lat"],
                    "center_lon": row["center_lon"],
                    "summary": row["summary"],
                    "key_themes": json.loads(row["key_themes_json"]) if row["key_themes_json"] else [],
                    "story_count": row["story_count"],
                    "date_range": row["date_range"],
                    "zoom_level": row["zoom_level"],
                }
            )

        print(f"[DEBUG] Returning {len(clusters)} clusters")
        response["clusters"] = clusters

    else:
        # Return individual locations
        cursor = conn.execute(
            """
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
            ORDER BY sl.resolution_confidence DESC
        """,
            (sw_lat, ne_lat, sw_lon, ne_lon),
        )

        locations = []
        for row in cursor.fetchall():
            # Truncate summary for mini popup
            summary_preview = (row["summary"] or "")[:100]
            if len(row["summary"] or "") > 100:
                summary_preview += "..."

            locations.append(
                {
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
                }
            )

        response["locations"] = locations

    conn.close()
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
    conn = get_db()

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
        conn.close()
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

    conn.close()
    return story


@app.get("/api/cluster/{cluster_id}")
def get_cluster(cluster_id: str) -> dict[str, Any]:
    """
    Get cluster details with all stories.

    Returns:
        - cluster_id, center_lat, center_lon
        - summary, key_themes, date_range, story_count
        - stories: list of stories with timeline data
    """
    conn = get_db()

    # Get cluster metadata
    cursor = conn.execute(
        """
        SELECT
            cluster_id,
            center_lat,
            center_lon,
            summary,
            key_themes_json,
            story_count,
            date_range,
            story_ids_json
        FROM location_clusters
        WHERE cluster_id = ?
    """,
        (cluster_id,),
    )

    cluster_row = cursor.fetchone()
    if not cluster_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

    cluster = {
        "cluster_id": cluster_row["cluster_id"],
        "center_lat": cluster_row["center_lat"],
        "center_lon": cluster_row["center_lon"],
        "summary": cluster_row["summary"],
        "key_themes": json.loads(cluster_row["key_themes_json"]) if cluster_row["key_themes_json"] else [],
        "story_count": cluster_row["story_count"],
        "date_range": cluster_row["date_range"],
    }

    # Get story IDs
    story_ids = json.loads(cluster_row["story_ids_json"])

    # Fetch stories
    placeholders = ",".join("?" * len(story_ids))
    cursor = conn.execute(
        f"""
        SELECT
            s.story_id,
            s.title,
            s.summary,
            s.parsed_date,
            sl.resolved_lat,
            sl.resolved_lon
        FROM stories s
        LEFT JOIN story_locations sl ON s.story_id = sl.story_id AND sl.loc_idx = 0
        WHERE s.story_id IN ({placeholders})
        ORDER BY s.parsed_date
    """,
        story_ids,
    )

    stories = []
    for row in cursor.fetchall():
        stories.append(
            {
                "story_id": row["story_id"],
                "title": row["title"],
                "summary": row["summary"],
                "date": row["parsed_date"],
                "lat": row["resolved_lat"],
                "lon": row["resolved_lon"],
            }
        )

    cluster["stories"] = stories

    conn.close()
    return cluster


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
