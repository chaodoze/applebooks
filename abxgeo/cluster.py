"""Cluster generation for geographic story visualization.

Generates narrative summaries for clusters of nearby stories using GPT-5-mini.
"""

import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add project root to path for baml_client imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import click  # noqa: E402
import numpy as np  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn  # noqa: E402
from sklearn.cluster import DBSCAN  # noqa: E402

from baml_client import b  # noqa: E402

console = Console()


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in meters."""
    from math import asin, cos, radians, sin, sqrt

    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))

    # Earth radius in meters
    r = 6371000

    return c * r


def create_clusters_table(db_path: Path) -> None:
    """Create location_clusters table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS location_clusters (
            cluster_id TEXT PRIMARY KEY,
            center_lat REAL NOT NULL,
            center_lon REAL NOT NULL,
            zoom_level INTEGER,
            story_ids_json TEXT NOT NULL,
            summary TEXT NOT NULL,
            key_themes_json TEXT,
            story_count INTEGER NOT NULL,
            date_range TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_location ON location_clusters(center_lat, center_lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clusters_zoom ON location_clusters(zoom_level)")
    conn.commit()
    conn.close()


def get_location_name(lat: float, lon: float, conn: sqlite3.Connection) -> str:
    """Get a human-readable location name from coordinates.

    Tries to find a resolved_address near the coordinates, or uses place_name.
    """
    cursor = conn.execute(
        """
        SELECT place_name, resolved_address
        FROM story_locations
        WHERE resolved_lat IS NOT NULL
        ORDER BY ABS(resolved_lat - ?) + ABS(resolved_lon - ?)
        LIMIT 1
    """,
        (lat, lon),
    )
    row = cursor.fetchone()
    if row:
        # Parse address to get city/region
        addr = row[1] or row[0] or f"{lat:.3f}, {lon:.3f}"
        # Extract city from address (simple heuristic)
        if "," in addr:
            parts = [p.strip() for p in addr.split(",")]
            # Try to get city + state/country (e.g., "Cupertino, CA" or "Beijing, China")
            if len(parts) >= 2:
                return f"{parts[-2]}, {parts[-1]}"
            return parts[0]
        return addr
    return f"{lat:.3f}, {lon:.3f}"


def cluster_locations(
    db_path: Path,
    min_stories: int = 3,
    address_eps_meters: float = 500,
    city_eps_meters: float = 5000,
    force: bool = False,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Cluster locations using DBSCAN.

    Args:
        db_path: Path to SQLite database
        min_stories: Minimum stories per cluster
        address_eps_meters: DBSCAN epsilon for address-level locations (meters)
        city_eps_meters: DBSCAN epsilon for city-level locations (meters)
        force: Regenerate all clusters (skip existing)
        verbose: Verbose output

    Returns:
        List of cluster dictionaries
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch all resolved locations with story metadata
    # Use first location per story to avoid duplicates in clusters
    cursor = conn.execute(
        """
        SELECT
            sl.story_id,
            sl.place_name,
            sl.resolved_lat,
            sl.resolved_lon,
            sl.resolved_precision,
            s.title,
            s.summary,
            s.parsed_date
        FROM story_locations sl
        JOIN stories s ON sl.story_id = s.story_id
        WHERE sl.resolved_lat IS NOT NULL
        ORDER BY sl.story_id, sl.loc_idx
    """
    )
    all_locations = [dict(row) for row in cursor.fetchall()]

    # Deduplicate: keep only first location per story
    seen_stories = set()
    locations = []
    for loc in all_locations:
        if loc["story_id"] not in seen_stories:
            locations.append(loc)
            seen_stories.add(loc["story_id"])

    if not locations:
        console.print("[yellow]No resolved locations found[/yellow]")
        conn.close()
        return []

    console.print(f"[cyan]Found {len(all_locations)} resolved locations ({len(locations)} unique stories)[/cyan]")

    # Separate by precision level
    address_locs = [loc for loc in locations if loc["resolved_precision"] in ("address", "street")]
    city_locs = [loc for loc in locations if loc["resolved_precision"] in ("city", "region")]

    console.print(f"[dim]  {len(address_locs)} address-level, {len(city_locs)} city-level[/dim]\n")

    all_clusters = []

    # Cluster address-level locations (tight clustering)
    if address_locs:
        coords = np.array([[loc["resolved_lat"], loc["resolved_lon"]] for loc in address_locs])

        # Convert eps from meters to degrees (rough approximation at mid-latitudes)
        # 1 degree latitude ≈ 111km, 1 degree longitude ≈ 111km * cos(lat)
        eps_deg = address_eps_meters / 111000

        clustering = DBSCAN(eps=eps_deg, min_samples=min_stories, metric="euclidean").fit(coords)

        # Group by cluster label
        cluster_groups = defaultdict(list)
        for i, label in enumerate(clustering.labels_):
            if label != -1:  # Skip noise points
                cluster_groups[label].append(address_locs[i])

        console.print(f"[green]Found {len(cluster_groups)} address-level clusters[/green]")

        for label, cluster_locs in cluster_groups.items():
            # Calculate center
            center_lat = np.mean([loc["resolved_lat"] for loc in cluster_locs])
            center_lon = np.mean([loc["resolved_lon"] for loc in cluster_locs])

            all_clusters.append(
                {
                    "center_lat": center_lat,
                    "center_lon": center_lon,
                    "locations": cluster_locs,
                    "zoom_level": 13,  # Street view
                    "precision_type": "address",
                }
            )

    # Cluster city-level locations (loose clustering)
    if city_locs:
        coords = np.array([[loc["resolved_lat"], loc["resolved_lon"]] for loc in city_locs])

        eps_deg = city_eps_meters / 111000

        clustering = DBSCAN(eps=eps_deg, min_samples=min_stories, metric="euclidean").fit(coords)

        cluster_groups = defaultdict(list)
        for i, label in enumerate(clustering.labels_):
            if label != -1:
                cluster_groups[label].append(city_locs[i])

        console.print(f"[green]Found {len(cluster_groups)} city-level clusters[/green]\n")

        for label, cluster_locs in cluster_groups.items():
            center_lat = np.mean([loc["resolved_lat"] for loc in cluster_locs])
            center_lon = np.mean([loc["resolved_lon"] for loc in cluster_locs])

            all_clusters.append(
                {
                    "center_lat": center_lat,
                    "center_lon": center_lon,
                    "locations": cluster_locs,
                    "zoom_level": 10,  # City view
                    "precision_type": "city",
                }
            )

    # Merge overlapping clusters: if city cluster is within 5km of address cluster, merge into address cluster
    address_clusters = [c for c in all_clusters if c["precision_type"] == "address"]
    city_clusters = [c for c in all_clusters if c["precision_type"] == "city"]

    merged_clusters = list(address_clusters)  # Start with all address clusters
    merge_threshold_meters = 5000  # 5km

    for city_cluster in city_clusters:
        # Check if this city cluster overlaps with any address cluster
        merged = False
        for addr_cluster in address_clusters:
            distance = haversine_distance(
                city_cluster["center_lat"],
                city_cluster["center_lon"],
                addr_cluster["center_lat"],
                addr_cluster["center_lon"],
            )

            if distance < merge_threshold_meters:
                # Merge city cluster into address cluster
                addr_cluster["locations"].extend(city_cluster["locations"])
                # Recalculate center with merged locations
                addr_cluster["center_lat"] = np.mean([loc["resolved_lat"] for loc in addr_cluster["locations"]])
                addr_cluster["center_lon"] = np.mean([loc["resolved_lon"] for loc in addr_cluster["locations"]])
                merged = True
                console.print(
                    f"[dim]  Merged city cluster ({len(city_cluster['locations'])} stories) "
                    f"into address cluster (now {len(addr_cluster['locations'])} stories)[/dim]"
                )
                break

        # If city cluster didn't overlap with any address cluster, keep it
        if not merged:
            merged_clusters.append(city_cluster)

    console.print(f"[green]After city→address merge: {len(merged_clusters)} total clusters[/green]")

    # Second merge pass: merge overlapping address-level clusters (within 5km)
    # This handles cases where DBSCAN created multiple address clusters in the same area
    final_clusters = []
    merged_indices = set()

    for i, cluster_a in enumerate(merged_clusters):
        if i in merged_indices:
            continue

        # Check if this cluster should be merged with any later cluster
        merged_with = []
        for j, cluster_b in enumerate(merged_clusters[i + 1 :], start=i + 1):
            if j in merged_indices:
                continue

            distance = haversine_distance(
                cluster_a["center_lat"],
                cluster_a["center_lon"],
                cluster_b["center_lat"],
                cluster_b["center_lon"],
            )

            if distance < merge_threshold_meters:
                merged_with.append(j)
                merged_indices.add(j)

        # If we found clusters to merge, create a new merged cluster
        if merged_with:
            all_locations = cluster_a["locations"][:]
            for j in merged_with:
                all_locations.extend(merged_clusters[j]["locations"])

            merged_cluster = {
                "center_lat": np.mean([loc["resolved_lat"] for loc in all_locations]),
                "center_lon": np.mean([loc["resolved_lon"] for loc in all_locations]),
                "locations": all_locations,
                "zoom_level": 13,  # Keep street zoom for merged address clusters
                "precision_type": "address",
            }
            final_clusters.append(merged_cluster)
            console.print(
                f"[dim]  Merged {len(merged_with) + 1} overlapping clusters "
                f"(now {len(all_locations)} stories total)[/dim]"
            )
        else:
            final_clusters.append(cluster_a)

    console.print(f"[green]After address→address merge: {len(final_clusters)} total clusters[/green]\n")

    conn.close()
    return final_clusters


async def summarize_cluster(cluster: dict[str, Any], location_name: str, verbose: bool = False) -> dict[str, Any]:
    """Generate narrative summary for a cluster using BAML + GPT-5-mini.

    Args:
        cluster: Cluster dictionary with 'locations' list
        location_name: Human-readable location name
        verbose: Verbose output

    Returns:
        Dictionary with summary, key_themes, date_range, story_count
    """
    # Format stories for BAML
    story_strings = []
    for loc in cluster["locations"]:
        date_str = loc["parsed_date"] or "unknown date"
        summary = (loc["summary"] or "No summary")[:200]  # Truncate to 200 chars
        story_strings.append(f"{loc['title']} ({date_str}) | {summary}")

    if verbose:
        console.print(f"[dim]Summarizing {len(story_strings)} stories at {location_name}...[/dim]")

    try:
        # Call BAML function (async)
        result = await b.SummarizeCluster(
            stories=story_strings, location_name=location_name, zoom_level=cluster["zoom_level"]
        )

        return {
            "summary": result.summary,
            "key_themes": result.key_themes,
            "date_range": result.date_range,
            "story_count": result.story_count,
        }

    except Exception as e:
        console.print(f"[red]Error summarizing cluster at {location_name}: {str(e)[:100]}[/red]")
        # Fallback: simple summary
        dates = [loc["parsed_date"] for loc in cluster["locations"] if loc["parsed_date"]]
        date_range = f"{min(dates)}-{max(dates)}" if len(dates) > 1 else dates[0] if dates else "unknown"

        return {
            "summary": f"{len(cluster['locations'])} stories at {location_name} spanning {date_range}.",
            "key_themes": [],
            "date_range": date_range,
            "story_count": len(cluster["locations"]),
        }


def save_cluster(db_path: Path, cluster: dict[str, Any], summary: dict[str, Any]) -> str:
    """Save cluster to database.

    Args:
        db_path: Path to SQLite database
        cluster: Cluster dictionary
        summary: Summary dictionary from summarize_cluster

    Returns:
        cluster_id
    """
    # Generate deterministic cluster_id from story_ids
    story_ids = sorted([loc["story_id"] for loc in cluster["locations"]])
    cluster_hash = hashlib.sha256(json.dumps(story_ids, sort_keys=True).encode()).hexdigest()[:16]
    cluster_id = f"cluster_{cluster_hash}"

    conn = sqlite3.connect(db_path)

    conn.execute(
        """
        INSERT OR REPLACE INTO location_clusters (
            cluster_id, center_lat, center_lon, zoom_level,
            story_ids_json, summary, key_themes_json,
            story_count, date_range
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            cluster_id,
            cluster["center_lat"],
            cluster["center_lon"],
            cluster["zoom_level"],
            json.dumps(story_ids),
            summary["summary"],
            json.dumps(summary["key_themes"]),
            summary["story_count"],
            summary["date_range"],
        ),
    )

    conn.commit()
    conn.close()

    return cluster_id


@click.command()
@click.option("--db", required=True, type=click.Path(exists=True, path_type=Path), help="Path to SQLite database")
@click.option("--min-stories", default=3, type=int, help="Minimum stories per cluster (default: 3)")
@click.option(
    "--address-eps", default=500, type=float, help="DBSCAN epsilon for address-level locations in meters (default: 500)"
)
@click.option(
    "--city-eps", default=5000, type=float, help="DBSCAN epsilon for city-level locations in meters (default: 5000)"
)
@click.option("--force", is_flag=True, help="Regenerate all clusters (skip existing)")
@click.option("--verbose", is_flag=True, help="Verbose output")
def cluster(
    db: Path,
    min_stories: int,
    address_eps: float,
    city_eps: float,
    force: bool,
    verbose: bool,
):
    """
    Generate geographic clusters and LLM summaries for story visualization.

    This command:
    1. Groups nearby locations using DBSCAN clustering
    2. Generates narrative summaries using GPT-5-mini via BAML
    3. Stores results in location_clusters table

    Examples:
        # Generate clusters with default settings
        abxgeo cluster --db library.sqlite

        # Use tighter clustering for address-level
        abxgeo cluster --db library.sqlite --address-eps 300

        # Regenerate all clusters
        abxgeo cluster --db library.sqlite --force
    """
    console.print("[bold cyan]ABXGeo - Cluster Generation[/bold cyan]\n")

    # Create table if needed
    create_clusters_table(db)

    # Check if clusters already exist (unless --force)
    if not force:
        conn = sqlite3.connect(db)
        cursor = conn.execute("SELECT COUNT(*) FROM location_clusters")
        existing_count = cursor.fetchone()[0]
        conn.close()

        if existing_count > 0:
            console.print(
                f"[yellow]Found {existing_count} existing clusters. Use --force to regenerate.[/yellow]\n"
                f"[dim]Run 'abxgeo stats --db {db}' to see cluster statistics[/dim]"
            )
            sys.exit(0)

    # Cluster locations
    console.print(f"[cyan]Clustering locations (address eps={address_eps}m, city eps={city_eps}m)...[/cyan]\n")
    clusters = cluster_locations(
        db_path=db,
        min_stories=min_stories,
        address_eps_meters=address_eps,
        city_eps_meters=city_eps,
        force=force,
        verbose=verbose,
    )

    if not clusters:
        console.print("[yellow]No clusters found (need at least {min_stories} stories per location)[/yellow]")
        sys.exit(0)

    console.print(f"[green]Generated {len(clusters)} clusters[/green]\n")

    # Generate summaries
    conn = sqlite3.connect(db)
    saved_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
    ) as progress_bar:
        task = progress_bar.add_task(f"Generating summaries for {len(clusters)} clusters...", total=len(clusters))

        for cluster in clusters:
            # Get location name
            location_name = get_location_name(cluster["center_lat"], cluster["center_lon"], conn)

            # Generate summary
            summary = summarize_cluster(cluster, location_name, verbose=verbose)

            # Save to database
            cluster_id = save_cluster(db, cluster, summary)
            saved_count += 1

            if verbose:
                console.print(
                    f"[dim]  Saved {cluster_id}: {summary['story_count']} stories, {summary['date_range']}[/dim]"
                )

            progress_bar.update(task, advance=1)

    conn.close()

    console.print(f"\n[green]✓ Successfully generated {saved_count} clusters[/green]")
    console.print(f"[dim]Run 'abxgeo stats --db {db}' to see statistics[/dim]")


if __name__ == "__main__":
    cluster()
