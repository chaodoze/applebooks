"""Rate limiting utilities for API calls."""

import asyncio
import time
from collections import deque


class RateLimiter:
    """Token bucket rate limiter with asyncio support."""

    def __init__(self, max_concurrent: int, requests_per_second: float | None = None):
        """
        Initialize rate limiter.

        Args:
            max_concurrent: Maximum number of concurrent requests
            requests_per_second: Optional rate limit (e.g., 1.0 for Nominatim)
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.requests_per_second = requests_per_second
        self.request_times: deque[float] = deque()

    async def acquire(self):
        """Acquire permission to make a request."""
        # First, acquire semaphore for concurrency control
        await self.semaphore.acquire()

        # Then, check rate limit if specified
        if self.requests_per_second:
            now = time.time()

            # Remove old requests outside the time window
            cutoff = now - 1.0  # 1 second window
            while self.request_times and self.request_times[0] < cutoff:
                self.request_times.popleft()

            # If we're at the rate limit, wait
            if len(self.request_times) >= self.requests_per_second:
                sleep_time = 1.0 - (now - self.request_times[0])
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                    now = time.time()

            # Record this request
            self.request_times.append(now)

    def release(self):
        """Release the semaphore."""
        self.semaphore.release()

    async def __aenter__(self):
        """Context manager entry."""
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


# Global rate limiters for different services
OPENAI_LIMITER = RateLimiter(max_concurrent=10)  # 10 concurrent, ~500 RPM capacity
GOOGLE_MAPS_LIMITER = RateLimiter(max_concurrent=50)  # 50 concurrent, 10k/day
NOMINATIM_LIMITER = RateLimiter(max_concurrent=1, requests_per_second=1.0)  # Strict: 1 req/sec
