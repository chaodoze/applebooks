"""Web harvester for geocoding - uses OpenAI search API + URL fetching + caching."""

import sqlite3
from datetime import datetime, timedelta

import requests
from openai import OpenAI

# Initialize OpenAI client (will use OPENAI_API_KEY env var)
client = OpenAI()


class WebHarvester:
    """Harvests address information from web search results."""

    def __init__(self, db_path: str, cache_ttl_days: int = 7):
        """
        Initialize web harvester.

        Args:
            db_path: Path to SQLite database
            cache_ttl_days: Number of days to cache URL content
        """
        self.db_path = db_path
        self.cache_ttl_days = cache_ttl_days

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search web using DuckDuckGo (simple, no API key needed).

        Args:
            query: Search query
            max_results: Maximum number of results to return

        Returns:
            List of search results with url, title, snippet
        """
        # Simple DuckDuckGo HTML search scraping
        # This is a fallback since OpenAI doesn't have direct web search
        try:
            from urllib.parse import quote_plus

            search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse results (very basic)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(response.text, "html.parser")

            results = []
            for result in soup.select(".result")[:max_results]:
                title_elem = result.select_one(".result__title")
                snippet_elem = result.select_one(".result__snippet")
                url_elem = result.select_one(".result__url")

                if title_elem and url_elem:
                    results.append(
                        {
                            "title": title_elem.get_text(strip=True),
                            "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                            "url": url_elem.get("href", ""),
                        }
                    )

            return results

        except Exception as e:
            print(f"Search failed: {e}")
            # Fallback: return mock result for testing
            return [
                {
                    "title": f"Search for: {query}",
                    "snippet": f"No search results available. Query: {query}",
                    "url": "https://www.google.com/search?q=" + quote_plus(query),
                }
            ]

    def fetch_url(self, url: str, use_cache: bool = True) -> str | None:
        """
        Fetch URL content with optional caching.

        Args:
            url: URL to fetch
            use_cache: Whether to use cached content if available

        Returns:
            URL content as text, or None if fetch failed
        """
        # Check cache first
        if use_cache:
            cached = self._get_cached_content(url)
            if cached:
                return cached

        # Fetch URL
        try:
            headers = {
                "User-Agent": "ABXGeo/1.0 (Apple Books Story Geocoding Bot; +https://github.com/yourusername/applebooks)"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            content = response.text

            # Cache the content
            self._cache_content(url, content)

            return content

        except requests.RequestException as e:
            print(f"Failed to fetch {url}: {e}")
            return None

    def harvest(self, query: str, max_results: int = 5) -> str:
        """
        Search and fetch content for a query.

        Args:
            query: Search query
            max_results: Maximum number of URLs to fetch

        Returns:
            Combined search results and URL content as formatted text
        """
        # Search
        search_results = self.search(query, max_results)

        if not search_results:
            return f"No search results found for query: {query}"

        # Build formatted output
        output_parts = [f"Search results for: {query}\n"]

        for i, result in enumerate(search_results, 1):
            url = result.get("url", "")
            title = result.get("title", "No title")
            snippet = result.get("snippet", "No snippet")

            output_parts.append(f"\n--- Result {i} ---")
            output_parts.append(f"Title: {title}")
            output_parts.append(f"URL: {url}")
            output_parts.append(f"Snippet: {snippet}")

            # Fetch full content
            if url:
                content = self.fetch_url(url)
                if content:
                    # Extract relevant portion (first 2000 chars to avoid token limits)
                    preview = content[:2000]
                    output_parts.append(f"Content preview: {preview}...")
                else:
                    output_parts.append("Content: [Failed to fetch]")

        return "\n".join(output_parts)

    def _get_cached_content(self, url: str) -> str | None:
        """Get cached URL content if not expired."""
        cutoff = datetime.now() - timedelta(days=self.cache_ttl_days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT content FROM geocode_cache
                WHERE url = ? AND datetime(fetched_at) > datetime(?)
                """,
                (url, cutoff.isoformat()),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def _cache_content(self, url: str, content: str) -> None:
        """Cache URL content."""
        import hashlib

        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO geocode_cache (url_hash, url, content, fetched_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (url_hash, url, content),
            )
            conn.commit()

    def clear_cache(self, older_than_days: int | None = None) -> int:
        """
        Clear cached content.

        Args:
            older_than_days: Only clear cache older than this many days.
                           If None, clear all cache.

        Returns:
            Number of entries cleared
        """
        with sqlite3.connect(self.db_path) as conn:
            if older_than_days is not None:
                cutoff = datetime.now() - timedelta(days=older_than_days)
                cursor = conn.execute(
                    "DELETE FROM geocode_cache WHERE cached_at < ?",
                    (cutoff.isoformat(),),
                )
            else:
                cursor = conn.execute("DELETE FROM geocode_cache")

            conn.commit()
            return cursor.rowcount
