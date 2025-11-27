"""Redis cache client with graceful fallback to in-memory cache.

Provides async cache operations with automatic fallback when Redis is unavailable.
Uses connection pooling and supports TTL-based expiration.
"""

import asyncio
import fnmatch
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend interface."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set value with optional TTL in seconds."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> list[str]:
        """Get keys matching pattern."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if backend is connected."""
        pass


class InMemoryCache(CacheBackend):
    """In-memory cache with TTL support.

    Used as fallback when Redis is unavailable.
    Data is lost on restart.
    """

    def __init__(self):
        self._store: dict[str, tuple[str, Optional[float]]] = {}  # key -> (value, expiry_time)
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        """Get or create the lock for the current event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get(self, key: str) -> Optional[str]:
        async with self._get_lock():
            if key not in self._store:
                return None
            value, expiry = self._store[key]
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        async with self._get_lock():
            expiry = time.time() + ttl if ttl else None
            self._store[key] = (value, expiry)
            return True

    async def delete(self, key: str) -> bool:
        async with self._get_lock():
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        async with self._get_lock():
            if key not in self._store:
                return False
            value, expiry = self._store[key]
            if expiry is not None and time.time() > expiry:
                del self._store[key]
                return False
            return True

    async def keys(self, pattern: str) -> list[str]:
        """Pattern matching using fnmatch (glob-style)."""
        async with self._get_lock():
            # Clean expired keys first
            now = time.time()
            expired = [k for k, (_, exp) in self._store.items() if exp is not None and now > exp]
            for k in expired:
                del self._store[k]

            # Glob-style pattern matching
            return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def close(self) -> None:
        self._store.clear()

    def is_connected(self) -> bool:
        return True


class RedisCache(CacheBackend):
    """Redis cache backend using redis-py async."""

    def __init__(self, url: str):
        self._url = url
        self._redis: Optional[Any] = None
        self._connected = False

    async def _ensure_connection(self) -> bool:
        """Ensure Redis connection is established."""
        if self._redis is not None and self._connected:
            return True

        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]

            self._redis = redis.from_url(
                self._url,
                encoding="utf-8",
                decode_responses=True,
            )
            # Test connection
            await self._redis.ping()
            self._connected = True
            # Redact credentials from URL for logging
            parsed = urlparse(self._url)
            safe_url = f"{parsed.hostname}:{parsed.port or 6379}"
            logger.info(f"Connected to Redis at {safe_url}")
            return True
        except ImportError:
            logger.warning("redis package not installed, falling back to in-memory cache")
            return False
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}, falling back to in-memory cache")
            self._connected = False
            return False

    async def get(self, key: str) -> Optional[str]:
        if not await self._ensure_connection():
            return None
        try:
            result: Optional[str] = await self._redis.get(key)  # type: ignore[union-attr]
            return result
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            self._connected = False
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            if ttl:
                await self._redis.setex(key, ttl, value)  # type: ignore[union-attr]
            else:
                await self._redis.set(key, value)  # type: ignore[union-attr]
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            self._connected = False
            return False

    async def delete(self, key: str) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            result: int = await self._redis.delete(key)  # type: ignore[union-attr]
            return result > 0
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            self._connected = False
            return False

    async def exists(self, key: str) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            result: int = await self._redis.exists(key)  # type: ignore[union-attr]
            return result > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error: {e}")
            self._connected = False
            return False

    async def keys(self, pattern: str) -> list[str]:
        if not await self._ensure_connection():
            return []
        try:
            # Use SCAN instead of KEYS to avoid blocking Redis
            result: list[str] = []
            cursor: int = 0
            while True:
                cursor, keys = await self._redis.scan(  # type: ignore[union-attr]
                    cursor, match=pattern, count=100
                )
                result.extend(keys)
                if cursor == 0:
                    break
            return result
        except Exception as e:
            logger.error(f"Redis SCAN error: {e}")
            self._connected = False
            return []

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
            self._connected = False

    def is_connected(self) -> bool:
        return self._connected


class CacheClient:
    """Cache client with automatic Redis -> in-memory fallback.

    Provides a unified interface that:
    1. Tries Redis first if REDIS_URL is configured
    2. Falls back to in-memory cache if Redis fails
    3. Supports JSON serialization for complex objects
    """

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._backend: Optional[CacheBackend] = None
        self._fallback: InMemoryCache = InMemoryCache()
        self._using_fallback = False

    async def _get_backend(self) -> CacheBackend:
        """Get the appropriate cache backend."""
        if self._backend is not None:
            if self._backend.is_connected():
                return self._backend
            # Backend disconnected, try to reconnect or fall back

        # Try Redis if URL is configured
        if self._redis_url:
            redis_backend = RedisCache(self._redis_url)
            if await redis_backend._ensure_connection():
                self._backend = redis_backend
                self._using_fallback = False
                return self._backend

        # Fall back to in-memory
        if not self._using_fallback:
            logger.info("Using in-memory cache (Redis not available)")
            self._using_fallback = True
        self._backend = self._fallback
        return self._backend

    async def get(self, key: str) -> Optional[str]:
        """Get string value by key."""
        backend = await self._get_backend()
        return await backend.get(key)

    async def get_json(self, key: str) -> Optional[Any]:
        """Get JSON-deserialized value by key."""
        value = await self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> bool:
        """Set string value with optional TTL."""
        backend = await self._get_backend()
        return await backend.set(key, value, ttl)

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set JSON-serialized value with optional TTL."""
        try:
            json_str = json.dumps(value, default=str)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON serialization error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key."""
        backend = await self._get_backend()
        return await backend.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        backend = await self._get_backend()
        return await backend.exists(key)

    async def keys(self, pattern: str) -> list[str]:
        """Get keys matching pattern."""
        backend = await self._get_backend()
        return await backend.keys(pattern)

    async def close(self) -> None:
        """Close all connections."""
        if self._backend:
            await self._backend.close()
        await self._fallback.close()

    def is_using_redis(self) -> bool:
        """Check if currently using Redis backend."""
        return not self._using_fallback


# Global cache client instance
_cache_client: Optional[CacheClient] = None


def get_cache_client() -> CacheClient:
    """Get or create the global cache client."""
    global _cache_client
    if _cache_client is None:
        _cache_client = CacheClient()
    return _cache_client


async def close_cache_client() -> None:
    """Close the global cache client."""
    global _cache_client
    if _cache_client:
        await _cache_client.close()
        _cache_client = None
