"""Cache module for Chimera.

Provides caching abstractions with pluggable backends (Redis, in-memory).
"""

from .redis_client import CacheClient, get_cache_client

__all__ = ["CacheClient", "get_cache_client"]
